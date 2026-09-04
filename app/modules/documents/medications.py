"""Stage 9b — correcting a misread medicine name, against a closed list, with a score.

This module is where the whole feature is most dangerous, so it is where the rules are
strictest. "Augmtin" is obviously Augmentin to a pharmacist. It is *also* obviously something
to a language model asked what drug it resembles — and the model will answer with the same
fluency whether the input was "Augmtin", "Augmntn" or a smudge, which is precisely the
property that makes it unusable here. A wrong medicine name that reads confidently is worse
than no medicine name at all, because no medicine name is visibly a gap and a wrong one is not.

So the correction is **constrained matching**, not generation:

1. The output can only ever be a string that already exists in
   `data/terminology/medications.json`. Nothing else can be produced, at any confidence.
2. Every correction carries the similarity that produced it, and the runner-up it beat.
3. A correction is applied automatically **only** when it is strong *and* unambiguous *and*
   the OCR was reasonably sure of the characters in the first place. Three conditions, all of
   which must hold — because each one alone has a failure mode the other two catch.
4. Anything short of that is returned as a *suggestion with the name left null*. The raw text
   stands, the candidate is offered, and a human decides. "Possible medication: Augmentin —
   91%" is a useful thing to put in front of a pharmacist. "Augmentin" would be a lie.
5. A token the OCR marked illegible is **never** auto-corrected, however well it scores. A
   confident match on characters that were not confidently read is a confident match on a
   guess.

This is not a CodeSystem and it emits no codes. Invariant 5 is untouched: nothing here ever
becomes a `Coding`, and the coding sidecar still goes through `emit_coding()` as it always did.
"""

from __future__ import annotations

import difflib
import functools
import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import settings
from app.modules.documents.sig import fold

#: How a name was resolved. The distinction between `abbreviation` and `normalised` matters to
#: a reader: one is a table lookup that is certain, the other is a similarity judgement.
MatchStatus = Literal["exact", "abbreviation", "normalised", "candidate", "illegible", "unknown"]

#: Characters an OCR layer uses to mark "I could not read this". A name containing one of
#: these has a hole in it, and a hole cannot be matched over — only guessed across.
ILLEGIBLE = re.compile(r"[?*·□■]|\.{2,}|_{2,}")

#: Glyph pairs a recogniser confuses, folded together before scoring so that "Pantop 4O" and
#: "Pantop 40" are not treated as different words. Not clinical content — a property of
#: character recognition — so it lives in code rather than in the YAML.
_CONFUSIONS = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "6": "G"})


@dataclass(frozen=True, slots=True)
class Candidate:
    """One dictionary entry that resembles the OCR string, and by how much."""

    display: str
    generic: str
    brand: str | None
    score: float
    #: The exact dictionary string that matched — a brand, a generic, or an abbreviation.
    matched_on: str
    matched_kind: Literal["generic", "brand", "abbreviation"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "display": self.display,
            "generic": self.generic,
            "brand": self.brand,
            "score": round(self.score, 3),
            "matchedOn": self.matched_on,
            "matchedKind": self.matched_kind,
        }


@dataclass(frozen=True, slots=True)
class NameMatch:
    """What the paper appears to say, what it probably means, and whether we are sure enough.

    `name is None` is a first-class outcome, not an error. It means: this is what was read, we
    are not confident enough to say what it is, here is what it might be, ask someone.
    """

    raw: str
    status: MatchStatus
    name: str | None
    generic: str | None
    brand: str | None
    confidence: float
    candidates: tuple[Candidate, ...]

    @property
    def needs_confirmation(self) -> bool:
        return self.name is None or self.status in ("candidate", "illegible")

    @property
    def resolved(self) -> bool:
        return self.name is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw,
            "status": self.status,
            "name": self.name,
            "generic": self.generic,
            "brand": self.brand,
            "confidence": round(self.confidence, 3),
            "needsConfirmation": self.needs_confirmation,
            "candidates": [c.to_dict() for c in self.candidates],
        }


@dataclass(frozen=True, slots=True)
class Entry:
    generic: str
    brands: tuple[str, ...]
    abbreviations: tuple[str, ...]
    forms: tuple[str, ...]
    strengths: tuple[str, ...]
    drug_class: str


@functools.lru_cache(maxsize=1)
def load_medications() -> tuple[Entry, ...]:
    path = settings.path(settings.terminology_seed_dir) / "medications.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        Entry(
            generic=item["generic"],
            brands=tuple(item.get("brands", [])),
            abbreviations=tuple(item.get("abbreviations", [])),
            forms=tuple(item.get("forms", [])),
            strengths=tuple(item.get("strengths", [])),
            drug_class=item.get("class", ""),
        )
        for item in payload["medications"]
    )


@functools.lru_cache(maxsize=1)
def _index() -> list[tuple[str, str, str, Entry]]:
    """Every searchable string in the dictionary as (folded, original, kind, entry).

    Flattened once. A brand and a generic are both legitimate things to find on a
    prescription and neither is privileged: a doctor writes "Pantop", the pharmacist reads
    "Pantop", and rendering it as "Pantoprazole" without also showing "Pantop" would make the
    read-back disagree with the paper in the patient's hand.
    """
    rows: list[tuple[str, str, str, Entry]] = []
    for entry in load_medications():
        rows.append((_score_key(entry.generic), entry.generic, "generic", entry))
        rows.extend((_score_key(b), b, "brand", entry) for b in entry.brands)
        rows.extend((_score_key(a), a, "abbreviation", entry) for a in entry.abbreviations)
    return rows


def _score_key(text: str) -> str:
    """Fold for comparison only, never for display (the rule carried from ADR-0004)."""
    return fold(text).translate(_CONFUSIONS)


def _similarity(left: str, right: str) -> float:
    """Character similarity between a folded OCR string and a folded dictionary string.

    `difflib`'s ratio is 2·(matching characters)/(total length of both), so it already carries
    the length comparison inside it — a short fragment against a long drug name scores low
    because the denominator is large. An explicit length penalty on top of it was tried and
    removed: it double-counted, and it dragged "Augmtin"/"Augmentin" from 0.88 down to 0.78,
    which is the difference between the worked example in the brief correcting cleanly and
    being demoted to a suggestion.

    Measured on the cases that matter: Augmtin/Augmentin 0.88, Metfomin/Metformin 0.89,
    Amlo/Amlodipine 0.57, Amo/Amoxicillin 0.43. The discrimination this module needs is
    already in the ratio.
    """
    if not left or not right:
        return 0.0
    return difflib.SequenceMatcher(None, left, right).ratio()


def _display_for(matched: str, kind: str, entry: Entry) -> str:
    """What to *call* it: the brand where a brand was written, the generic otherwise.

    An abbreviation resolves to the generic, because "PCM" is shorthand for the substance and
    printing "PCM" back at a patient teaches them nothing.
    """
    return matched if kind == "brand" else entry.generic


def match_name(raw: str, *, ocr_confidence: float = 1.0) -> NameMatch:
    """Resolve an OCR'd medicine name against the dictionary, or decline to.

    `ocr_confidence` is the recogniser's own confidence in the characters. It gates automatic
    correction but never the *offering* of candidates: a pharmacist looking at a badly-read
    line still benefits from "this might be Augmentin", as long as nothing has recorded that
    it is.
    """
    cleaned = raw.strip(" .,:;-")
    if not cleaned:
        return NameMatch(raw, "unknown", None, None, None, 0.0, ())

    illegible = ILLEGIBLE.search(cleaned) is not None
    key = _score_key(ILLEGIBLE.sub("", cleaned) if illegible else cleaned)
    if not key:
        return NameMatch(cleaned, "illegible", None, None, None, 0.0, ())

    scored = sorted(
        (
            Candidate(
                display=_display_for(original, kind, entry),
                generic=entry.generic,
                brand=original if kind == "brand" else None,
                score=_similarity(key, folded),
                matched_on=original,
                matched_kind=kind,  # type: ignore[arg-type]
            )
            for folded, original, kind, entry in _index()
        ),
        key=lambda c: c.score,
        reverse=True,
    )
    best = scored[0]
    runner_up = next((c for c in scored[1:] if c.generic != best.generic), None)
    margin = best.score - (runner_up.score if runner_up else 0.0)
    shortlist = tuple(
        c
        for c in scored[: settings.rx_name_candidate_limit]
        if c.score >= settings.rx_name_candidate_similarity
    )

    if illegible:
        # Rule 5. However well it scores, the characters it scored on are characters nobody
        # actually read. The suggestion is offered; the name is not filled in.
        return NameMatch(cleaned, "illegible", None, None, None, best.score, shortlist)

    if best.score >= 0.999:
        status: MatchStatus = "abbreviation" if best.matched_kind == "abbreviation" else "exact"
        return NameMatch(
            raw=cleaned,
            status=status,
            name=best.display,
            generic=best.generic,
            brand=best.brand,
            confidence=1.0,
            candidates=(),
        )

    auto = (
        best.score >= settings.rx_name_auto_similarity
        and margin >= settings.rx_name_margin
        and ocr_confidence >= settings.rx_name_min_ocr_confidence
        # The opening letters anchor the match. Handwriting garbles the middle of a word far
        # more often than its start, and without this "Zerodol" is a short hop from "Zerodol"
        # to any similarly-shaped name in the list.
        and key[:2] == _score_key(best.matched_on)[:2]
    )
    if auto:
        return NameMatch(
            raw=cleaned,
            status="normalised",
            name=best.display,
            generic=best.generic,
            brand=best.brand,
            # Never above the score itself, and never above what OCR was sure of. A correction
            # cannot be more certain than the characters it corrected.
            confidence=round(min(best.score, ocr_confidence), 3),
            candidates=shortlist[:1],
        )

    if shortlist:
        return NameMatch(cleaned, "candidate", None, None, None, best.score, shortlist)
    return NameMatch(cleaned, "unknown", None, None, None, best.score, ())


_NUMBER = re.compile(r"^\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>[a-zA-Z/%]+)?\s*$")


def strength_is_recognised(raw: str, match: NameMatch) -> bool | None:
    """Is this a strength this medicine is actually dispensed in?

    Returns `None` when the question cannot be asked — the medicine is unresolved, the number
    is unparseable, or the dictionary has no strengths listed for it. `None` is not `False`
    and the caller must not treat it as one.

    This is the check that catches a **misread dose**, which is the most dangerous single
    error the whole pipeline can make. Tesseract read "PCM 500 sos" off the handwritten
    fixture as "PCM 526 sos": the name resolved perfectly, the confidence was 0.80, and the
    line would have gone into the record as Paracetamol 526 with nothing anywhere suggesting
    a problem. 526 is not a strength paracetamol comes in, and that fact is sitting in the
    dictionary already.

    It deliberately does NOT correct the number. Nothing in this system may edit a dose: 526
    might be a compounded preparation, a strength the local formulary is missing, or simply a
    number the doctor wrote. It raises a hand, and a human looks.
    """
    if not match.resolved:
        return None
    parsed = _NUMBER.match(raw or "")
    if parsed is None:
        return None
    entry = next((e for e in load_medications() if e.generic == match.generic), None)
    if entry is None or not entry.strengths:
        return None
    value = parsed.group("value")
    known = {
        parsed_known.group("value")
        for known_strength in entry.strengths
        if (parsed_known := _NUMBER.match(known_strength))
    }
    return value in known


def infer_strength(raw: str, match: NameMatch) -> tuple[str, str] | None:
    """`625` + a resolved Augmentin → `("625 mg", "dictionary")`. Otherwise the raw text.

    Returns `(value, source)` where source is `ocr` when the unit was written on the paper and
    `dictionary` when it was supplied from the medication's known strengths.

    The inference is tightly bounded, and every part of the bound is load-bearing:

    * the medicine must already be **resolved** — inferring a unit for a drug we could not
      name is inferring it from nothing;
    * the number must match **exactly one** of that medicine's known strengths. Levothyroxine
      is dispensed in micrograms and Metformin in milligrams; a drug with "50 mg" and "50 mcg"
      both on its list gets no inference at all, because the two differ by a thousandfold.

    A unit that cannot be inferred is not invented. The number stands alone, which is exactly
    what the prescription says.
    """
    parsed = _NUMBER.match(raw or "")
    if parsed is None:
        return None
    if parsed.group("unit"):
        return raw.strip(), "ocr"
    if not match.resolved:
        return raw.strip(), "ocr"

    value = parsed.group("value")
    entry = next((e for e in load_medications() if e.generic == match.generic), None)
    if entry is None:
        return raw.strip(), "ocr"

    hits = [
        known
        for known in entry.strengths
        if (parsed_known := _NUMBER.match(known)) and parsed_known.group("value") == value
    ]
    if len(hits) == 1:
        return hits[0], "dictionary"
    return raw.strip(), "ocr"
