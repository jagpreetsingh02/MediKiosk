"""Stage 9a — dosing shorthand into words, by table lookup and nothing else.

**Rule, emphatically not LLM.** "BD" means twice daily on every prescription written in India
and it will still mean that next year. Resolving it with a language model would be slower,
non-reproducible, unavailable offline, and would occasionally return something else — and
"occasionally something else" applied to a dosing frequency is a patient taking a medicine
four times a day instead of twice.

Every entry lives in `data/terminology/prescription-abbreviations.yaml`, so a clinician can
correct the table without touching Python. The code here contains no clinical string at all;
if you find yourself about to write one, it belongs in the YAML.

The lookup is **exact**. Case and punctuation are folded away — `b.d.`, `BD` and `bd` are one
token — but there is no similarity scoring anywhere in this module. A token either is an
abbreviation the table knows or it is not, and "not" is a normal, frequent, safe answer that
leaves the raw text standing. Fuzzy matching belongs to `medications.py`, where it is bounded
by a closed vocabulary and reports a score; letting it leak into sig codes would mean "TDS"
quietly becoming "TDS-ish".

Two separations that look pedantic and are not:

* **Frequency is not timing.** "BD bf" is twice daily *and* before food. Collapsing them into
  one field loses one of the two instructions.
* **`SOS` is not a frequency.** "When you need it" has no times-per-day, and rendering it in a
  schedule is how a patient ends up taking a rescue medicine four times a day.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from typing import Any, Literal

import yaml

from app.core.config import settings

#: Where a normalised value came from. `verbatim` means the table had nothing and the raw text
#: is being passed through unchanged — which is honest, and is not the same as a translation.
Source = Literal["abbreviation", "positional", "verbatim", "dictionary"]


@dataclass(frozen=True, slots=True)
class Normalised:
    """One interpreted field, with what it was on the paper and how it got here.

    `raw` is never dropped. Everything downstream — the physician's evidence drawer, the
    patient read-back, the audit log — needs to be able to show the scrawl beside the reading,
    and a normalisation that discards its input cannot be checked by anyone.
    """

    raw: str
    display: str
    clinical: str
    source: Source
    confidence: float
    #: For positional notation: how many times a day, when that is knowable. `None` where it
    #: genuinely is not — "as needed" and "once weekly" both have no daily count, and zero
    #: would be a lie about both.
    times_per_day: int | None = None


@functools.lru_cache(maxsize=1)
def load_table() -> dict[str, Any]:
    path = settings.path(settings.terminology_seed_dir) / "prescription-abbreviations.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=1)
def _folded() -> dict[str, dict[str, dict[str, Any]]]:
    """Every category, keyed by its folded token, built once.

    Folding at load time rather than per lookup: this runs once per medication field on every
    document, and rebuilding the table for each was the kind of thing that turns a 40 ms
    ingest into a 400 ms one for no reason at all.
    """
    table = load_table()
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for category in ("frequency", "instruction", "timing", "route", "form", "duration_unit"):
        out[category] = {fold(key): value for key, value in table.get(category, {}).items()}
    return out


def fold(token: str) -> str:
    """`b.d.` → `BD`. Case, periods, spaces and hyphens carry no meaning in a sig code."""
    return re.sub(r"[^A-Z0-9]", "", token.upper())


def lookup(category: str, token: str) -> Normalised | None:
    """One exact table hit, or nothing. There is no third outcome and no partial credit."""
    entry = _folded().get(category, {}).get(fold(token))
    if entry is None:
        return None
    return Normalised(
        raw=token.strip(),
        display=entry["display"],
        clinical=entry["clinical"],
        source="abbreviation",
        # A table hit is a definition, not a guess. Anything below 1.0 here would be theatre
        # of the same kind as a text layer reporting 0.9 — see TextLayerOCR.LAYER_CONFIDENCE.
        confidence=1.0,
        times_per_day=entry.get("times_per_day"),
    )


_POSITIONAL = re.compile(r"^(\d)\s*-\s*(\d)\s*-\s*(\d)(?:\s*-\s*(\d))?$")


def normalise_positional(raw: str) -> Normalised | None:
    """`1-0-1` → twice a day, morning and night. The commonest notation on an Indian pad.

    Read positionally against the slot labels in the YAML: three digits are
    morning-afternoon-night, four are morning-afternoon-evening-night. A zero means "not in
    that slot", so `1-0-1` is two doses and `1-1-1` is three.

    A number other than 0 or 1 is a *count* of units in that slot ("2-0-2" is two tablets
    twice a day), and it is deliberately not folded into the frequency: how many to take is a
    dose, not a schedule, and merging them would render "2-0-2" as four times a day.
    """
    match = _POSITIONAL.match(raw.strip())
    if match is None:
        return None
    slots = [group for group in match.groups() if group is not None]
    labels = load_table()["positional_slots"].get(len(slots))
    if labels is None:
        return None

    taken = [label for label, value in zip(labels, slots, strict=True) if value != "0"]
    if not taken:
        # "0-0-0" is a stopped medicine, not a schedule. Saying so beats inventing one.
        return Normalised(
            raw=raw.strip(),
            display="not currently being taken",
            clinical="not currently being taken",
            source="positional",
            confidence=1.0,
            times_per_day=0,
        )
    joined = ", ".join(taken)
    return Normalised(
        raw=raw.strip(),
        display=(
            f"{len(taken)} times a day ({joined})"
            if len(taken) > 1
            else f"once a day ({joined})"
        ),
        clinical=f"{len(taken)}× daily ({joined})",
        source="positional",
        confidence=1.0,
        times_per_day=len(taken),
    )


def normalise_frequency(raw: str) -> Normalised | None:
    """A schedule, from positional notation or from the frequency table. Nothing else.

    Explicitly does **not** fall through to `instruction` or `timing`. "SOS" is not a
    frequency and "HS" is not a frequency, and a caller that wants those should ask for them
    by name — see `interpret_schedule()` for the one place that legitimately wants all three.
    """
    if not raw or not raw.strip():
        return None
    return normalise_positional(raw) or lookup("frequency", raw)


def normalise_instruction(raw: str) -> Normalised | None:
    return lookup("instruction", raw) if raw and raw.strip() else None


def normalise_timing(raw: str) -> Normalised | None:
    return lookup("timing", raw) if raw and raw.strip() else None


def normalise_route(raw: str) -> Normalised | None:
    return lookup("route", raw) if raw and raw.strip() else None


def normalise_form(raw: str) -> Normalised | None:
    return lookup("form", raw) if raw and raw.strip() else None


_DURATION = re.compile(r"^(?P<count>\d{1,3})\s*(?P<unit>[a-z]+)\.?$", re.IGNORECASE)


def normalise_duration(raw: str) -> Normalised | None:
    """`5d`, `5 days`, `2 wks` → "5 days", "2 weeks".

    The count is never touched — it is a number that was written on the paper and there is
    nothing to normalise about it. Only the unit is looked up, and an unknown unit returns
    nothing rather than a guess: "5 doses" and "5 days" are not interchangeable.
    """
    match = _DURATION.match(raw.strip()) if raw else None
    if match is None:
        return None
    unit = lookup("duration_unit", match.group("unit"))
    if unit is None:
        return None
    count = int(match.group("count"))
    # "1 days" reads as a typo and undermines everything around it.
    singular = unit.display.rstrip("s") if count == 1 else unit.display
    return Normalised(
        raw=raw.strip(),
        display=f"{count} {singular}",
        clinical=f"{count} {unit.clinical if count != 1 else unit.clinical.rstrip('s')}",
        source="abbreviation",
        confidence=1.0,
    )


@dataclass(frozen=True, slots=True)
class Schedule:
    """Everything a prescription line says about *when*, kept in its three separate parts."""

    frequency: Normalised | None = None
    timing: Normalised | None = None
    instruction: Normalised | None = None

    def sentence(self) -> str:
        """The three parts as one instruction a patient can follow.

        Order is fixed — schedule, then when in the day, then the condition — because
        "twice a day, before food, only when you need it" is readable and any other
        permutation of the same three clauses is not.
        """
        parts = [
            part.display
            for part in (self.frequency, self.timing, self.instruction)
            if part is not None
        ]
        return ", ".join(parts)


def interpret_schedule(tokens: list[str]) -> Schedule:
    """Sort a line's leftover tokens into schedule, timing and condition.

    Each category is filled by the first token that matches it, and a token that matches
    nothing is simply left alone. A line with two frequencies on it is a line that was
    misread, and taking the first is no worse than any other choice — but silently
    concatenating them would produce an instruction that appears on no prescription.
    """
    frequency = timing = instruction = None
    for token in tokens:
        if frequency is None:
            frequency = normalise_frequency(token)
            if frequency is not None:
                continue
        if timing is None:
            timing = normalise_timing(token)
            if timing is not None:
                continue
        if instruction is None:
            instruction = normalise_instruction(token)
    return Schedule(frequency=frequency, timing=timing, instruction=instruction)
