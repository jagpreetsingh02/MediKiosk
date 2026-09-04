"""Stage 10 — a transcription becomes a prescription a patient can follow.

The output of this module is two things kept deliberately side by side:

* **what the paper appears to say** — the raw OCR line, unedited, including its mistakes;
* **what MediKiosk read it as** — the structured, normalised interpretation.

They are never merged, and the second never replaces the first anywhere in the system. That
is the whole safety model of this feature in one sentence: a reader can always see the
original and judge the interpretation against it, so an interpretation that is wrong is
*visibly* wrong rather than authoritative.

**Rule, not LLM.** A prescription line has a grammar — form, name, strength, dose, schedule,
duration — and this reads it with a tokeniser and two lookup tables. The one judgement call in
the whole pipeline, correcting a misread name, is delegated to `medications.py`, where it is
bounded by a closed vocabulary, scored, and refused whenever it is not clearly right.

**Nothing is invented.** Every field is either read off the line, resolved through a
deterministic table, or left null. There is one inference in the module —
`medications.infer_strength`, which supplies "mg" to a bare "625" — and it is allowed only
when the medicine is already resolved and exactly one of its known strengths has that number.
A field that cannot be filled is left null and said to be null. Null is not a failure here;
a confidently wrong value is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.modules.documents.backends import OCRResult
from app.modules.documents.medications import NameMatch, infer_strength, match_name
from app.modules.documents.ranges import match_analyte
from app.modules.documents.sig import (
    Normalised,
    fold,
    normalise_duration,
    normalise_form,
    normalise_frequency,
    normalise_instruction,
    normalise_route,
)

#: Number plus a dosing unit. `%` and `IU` are here because ointments and insulin are
#: prescribed in them and a strength parser that only knows mg silently drops both.
STRENGTH = re.compile(
    r"^(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mg|mcg|ug|g|ml|l|iu|units?|%|mg/ml|g/ml)$",
    re.IGNORECASE,
)
BARE_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")
#: `x`, `×` and `for` all introduce a duration on a real prescription.
DURATION_MARKER = re.compile(r"^(?:x|×|\*|for)$", re.IGNORECASE)
DURATION_TOKEN = re.compile(r"^(?P<count>\d{1,3})\s*(?P<unit>[a-z]{1,7})\.?$", re.IGNORECASE)
#: `1 tab`, `2 caps`, `5 ml`, `2 puffs` — how much to take, which is not the strength.
AMOUNT = re.compile(
    r"^(?P<count>\d+(?:\.\d+)?|½|1/2)\s*"
    r"(?P<unit>tabs?|tablets?|caps?|capsules?|ml|puffs?|drops?|sachets?|units?|tsp|scoops?)\.?$",
    re.IGNORECASE,
)

#: Lines that are page furniture. A prescription header carries numbers and capitalised words
#: and will otherwise parse as a drug — "Reg No. TN/12345" is a name and a number.
HEADER = re.compile(
    r"^\s*(?:date|dated|name|patient|age|sex|gender|reg(?:n|istration)?\s*(?:no|number)?|"
    r"opd|uhid|mrn|ip\s*no|dr\.?|doctor|address|ph(?:one)?|mob(?:ile)?|clinic|hospital|"
    r"diagnosis|dx|impression|advice|advise|follow\s*up|review|signature|rx|"
    r"complaints?|c/o|investigations?|sample|specimen|collected|report(?:ed)?|results?|ref(?:erred)?\s*by|bill|receipt|total|amount)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Field:
    """One interpreted value, with what it was on the paper and how it got that way.

    `raw` is what the OCR produced. `value` is what it was understood as. `source` says which
    of the two did the work, so a reader can tell "this is what the paper says" from "this is
    a table lookup" from "this came from the medication dictionary" — three quite different
    claims that would otherwise all render as plain text.
    """

    value: str
    raw: str
    #: ocr | abbreviation | positional | dictionary
    source: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "raw": self.raw,
            "source": self.source,
            "confidence": round(self.confidence, 3),
        }


def _from(normalised: Normalised | None, *, ocr_confidence: float) -> Field | None:
    if normalised is None:
        return None
    return Field(
        value=normalised.display,
        raw=normalised.raw,
        source=normalised.source,
        # A table lookup is certain about the *meaning*; it is not certain the characters
        # were read correctly, and it cannot be more confident than the recognition beneath it.
        confidence=min(normalised.confidence, ocr_confidence),
    )


@dataclass(slots=True)
class InterpretedMedication:
    """One prescription line, read twice: literally, and for meaning."""

    raw_text: str
    ocr_confidence: float
    name_match: NameMatch
    page: int = 1
    fields: dict[str, Field] = field(default_factory=dict)
    #: True when a human must look at this before it can be trusted.
    needs_verification: bool = True
    engine: str = ""

    @property
    def interpretation_confidence(self) -> float:
        """How sure the *reading* is, independent of how sure the *recognition* was.

        The weakest interpreted field, not the average. A line with a confident name and an
        unreadable dose is not a 0.8 line — it is a line whose dose nobody can trust, and
        averaging is exactly how that disappears.
        """
        if not self.name_match.resolved:
            # We did not interpret the name at all. Scoring the line on its dose alone would
            # report 0.9 for a medicine nobody could identify, which is the exact shape of
            # over-confidence this module exists to prevent.
            return 0.0
        scores = [f.confidence for f in self.fields.values()]
        scores.append(self.name_match.confidence)
        return round(min(scores), 3)

    def readable(self) -> dict[str, str | None]:
        """The flat, patient-facing shape: what to take, how much, how often, for how long."""
        return {
            "name": self.name_match.name,
            "generic": self.name_match.generic,
            "brand": self.name_match.brand,
            "strength": self._value("strength"),
            "dose": self._value("dose"),
            "form": self._value("form"),
            "frequency": self._value("frequency"),
            "duration": self._value("duration"),
            "route": self._value("route"),
            "timing": self._value("timing"),
            "instruction": self._value("instruction"),
        }

    def _value(self, key: str) -> str | None:
        found = self.fields.get(key)
        return found.value if found else None

    def _unidentified_head(self) -> str:
        """How to name a medicine we could not name.

        Three distinct states, and flattening them would lose the one useful thing each says:
        a suggestion worth showing, a name read but not recognised, and characters that were
        never read. "Possibly Augmentin" is help. "Augmentin" would be a claim.
        """
        raw = self.name_match.raw
        if self.name_match.candidates:
            best = self.name_match.candidates[0]
            return f'possibly {best.display} (read as "{raw}")'
        if self.name_match.status == "illegible":
            return f'unreadable medicine name ("{raw}")'
        return f'unrecognised medicine ("{raw}")'

    def sentence(self) -> str:
        """One line a patient can act on, built only from what was actually found.

        Assembled by joining the parts that exist rather than by filling a template, because a
        template produces "Take  for " when half the line was unreadable, and a patient
        reading that learns nothing except that the machine is broken.
        """
        readable = self.readable()
        head = readable["name"] or self._unidentified_head()
        if readable["strength"]:
            head = f"{head} {readable['strength']}"
        clauses: list[str] = []
        if readable["dose"]:
            clauses.append(f"take {readable['dose']}")
        for key in ("frequency", "timing", "instruction", "route"):
            if readable[key]:
                clauses.append(str(readable[key]))
        if readable["duration"]:
            clauses.append(f"for {readable['duration']}")
        return f"{head} — {', '.join(clauses)}" if clauses else head

    def to_dict(self) -> dict[str, Any]:
        return {
            "rawText": self.raw_text,
            "page": self.page,
            "engine": self.engine,
            "medication": self.readable(),
            "fields": {key: value.to_dict() for key, value in self.fields.items()},
            "nameMatch": self.name_match.to_dict(),
            "ocrConfidence": round(self.ocr_confidence, 3),
            "interpretationConfidence": self.interpretation_confidence,
            "needsVerification": self.needs_verification,
            "sentence": self.sentence(),
        }


@dataclass(slots=True)
class PrescriptionReading:
    """The whole document: what it says, what we made of it, and every line in between."""

    raw_ocr_text: str
    medications: list[InterpretedMedication] = field(default_factory=list)
    backend: str = ""

    @property
    def interpreted_text(self) -> str:
        if not self.medications:
            return ""
        return "\n".join(med.sentence() for med in self.medications)

    @property
    def needs_verification(self) -> bool:
        return any(med.needs_verification for med in self.medications)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rawOcrText": self.raw_ocr_text,
            "interpretedText": self.interpreted_text,
            "medications": [med.to_dict() for med in self.medications],
            "backend": self.backend,
            "needsVerification": self.needs_verification,
            "unresolvedCount": sum(
                1 for med in self.medications if not med.name_match.resolved
            ),
        }


def _tokens(line: str) -> list[str]:
    """Split a line into the pieces a prescription is written in.

    `1-0-1` survives as one token — it is a single instruction, and splitting it on the hyphen
    produces three meaningless numbers. `625mg` is split into `625` and `mg` so the strength
    parser sees the same shape whether or not the doctor left a space.
    """
    spaced = re.sub(r"(\d)([a-zA-Z]{1,4})\b", r"\1 \2", line)
    spaced = re.sub(r"\b([a-zA-Z]+)\.(?=\s|$)", r"\1", spaced)
    return [t for t in re.split(r"[\s,;()\[\]]+", spaced) if t]


def _is_sig_token(token: str) -> bool:
    """Whether a token is dosing shorthand rather than part of the medicine's name."""
    return any(
        f(token) is not None
        for f in (normalise_frequency, normalise_instruction, normalise_route, normalise_form)
    ) or _is_timing(token)


def _is_timing(token: str) -> bool:
    from app.modules.documents.sig import normalise_timing

    return normalise_timing(token) is not None


def parse_line(
    text: str, *, ocr_confidence: float, page: int = 1, engine: str = ""
) -> InterpretedMedication | None:
    """Read one line as a medication, or decide it is not one.

    Returns `None` for page furniture and for lines with nothing drug-shaped on them. A
    prescription is mostly not medicines — it is a letterhead, a patient block, a diagnosis
    and an advice line — and a parser that finds a drug on every line finds four drugs that
    are not there for every one that is.
    """
    line = text.strip()
    if len(line) < 3 or HEADER.match(line):
        return None

    tokens = _tokens(line)
    if not tokens:
        return None

    fields: dict[str, Field] = {}
    name_parts: list[str] = []
    remaining: list[str] = []

    # A leading form word ("TAB.", "CAP") is a form, not the start of the name.
    index = 0
    leading_form = normalise_form(tokens[0]) if tokens else None
    if leading_form is not None:
        found = _from(leading_form, ocr_confidence=ocr_confidence)
        if found:
            fields["form"] = found
        index = 1

    # The name is the run of word-tokens before the first number or sig code.
    while index < len(tokens):
        token = tokens[index]
        if BARE_NUMBER.match(token) or STRENGTH.match(token) or _is_sig_token(token):
            break
        if not any(ch.isalpha() for ch in token):
            break
        name_parts.append(token)
        index += 1
    remaining = tokens[index:]

    if not name_parts:
        return None

    raw_name = " ".join(name_parts)
    # A "name" this long is a sentence — an advice line, a diagnosis, a footer.
    if len(name_parts) > 4 or len(raw_name) > 48:
        return None

    _read_tail(remaining, fields, ocr_confidence=ocr_confidence)

    name_match = match_name(raw_name, ocr_confidence=ocr_confidence)
    strength_field = fields.get("strength")
    if strength_field is not None and strength_field.source == "bare":
        # Only a bare number can gain a unit from the dictionary. A strength that arrived
        # with its own unit keeps the parsed value — routing it back through inference
        # returned the unparsed raw text and reinstated "500 MG" over "500 mg".
        inferred = infer_strength(strength_field.raw, name_match)
        value, source = inferred if inferred else (strength_field.value, "ocr")
        fields["strength"] = Field(
            value=value,
            raw=strength_field.raw,
            source=source,
            confidence=strength_field.confidence,
        )

    # An analyte is never a medicine. "Haemoglobin 9.4 g/dL (12.0 - 15.0)" is a lab result,
    # and without this guard every line of a blood report parsed as an unidentified drug —
    # seven phantom medicines on the physician's verification screen from one report. The
    # check uses the same reference-range table the investigation extractor does, so the two
    # cannot drift apart.
    if match_analyte(raw_name):
        return None

    # Drug-shaped: something on the line has to say it is a medicine.
    if name_match.resolved:
        # A name from the dictionary is itself the evidence. A strength, schedule or form
        # confirms it; a bare recognised name with none of them is a heading.
        if not fields.keys() & {"strength", "frequency", "form", "dose", "timing", "instruction"}:
            return None
    else:
        # An UNRESOLVED name needs dosing shorthand, not merely a number. This is the
        # distinction that separates a prescription line from a lab line: both carry a word
        # and a number, and only one of them says when to take something. Accepting a bare
        # number here is exactly what turned a blood report into a list of medicines.
        if not fields.keys() & {"frequency", "instruction", "timing", "route", "form"}:
            return None

    medication = InterpretedMedication(
        raw_text=line,
        ocr_confidence=ocr_confidence,
        name_match=name_match,
        page=page,
        fields=fields,
        engine=engine,
    )
    medication.needs_verification = _needs_verification(medication)
    return medication


def _read_tail(
    tokens: list[str], fields: dict[str, Field], *, ocr_confidence: float
) -> None:
    """Fill strength, dose, schedule, duration and route from the tokens after the name.

    Order of tests per token is deliberate and each precedence has a reason. `5 ml` is a dose
    before it is a strength, because a syrup's strength is printed per 5 ml and the number on
    the line is what to swallow. A duration marker consumes the token that follows it, so
    "x 5 days" cannot be read as a dose of five.
    """
    from app.modules.documents.sig import normalise_timing

    expecting_duration = False
    position = 0
    while position < len(tokens):
        token = tokens[position]
        joined = " ".join(tokens[position : position + 2])

        if DURATION_MARKER.match(token):
            expecting_duration = True
            position += 1
            continue

        if expecting_duration:
            duration = normalise_duration(joined) or normalise_duration(token)
            if duration is not None:
                found = _from(duration, ocr_confidence=ocr_confidence)
                if found:
                    fields["duration"] = found
                position += 2 if normalise_duration(joined) is not None else 1
                expecting_duration = False
                continue
            expecting_duration = False

        amount = AMOUNT.match(token) or AMOUNT.match(joined)
        if amount and "dose" not in fields:
            fields["dose"] = Field(
                value=f"{amount.group('count')} {amount.group('unit').lower()}",
                raw=amount.group(0),
                source="ocr",
                confidence=ocr_confidence,
            )
            position += 2 if AMOUNT.match(joined) and not AMOUNT.match(token) else 1
            continue

        strength = STRENGTH.match(token) or STRENGTH.match(joined)
        if strength and "strength" not in fields:
            fields["strength"] = Field(
                value=f"{strength.group('value')} {strength.group('unit').lower()}",
                raw=strength.group(0),
                source="ocr",
                confidence=ocr_confidence,
            )
            position += 2 if STRENGTH.match(joined) and not STRENGTH.match(token) else 1
            continue

        for key, normaliser in (
            ("frequency", normalise_frequency),
            ("timing", normalise_timing),
            ("instruction", normalise_instruction),
            ("route", normalise_route),
            ("form", normalise_form),
        ):
            if key in fields:
                continue
            found = _from(normaliser(token), ocr_confidence=ocr_confidence)
            if found is not None:
                fields[key] = found
                break
        else:
            # A standalone `5d` with no marker in front of it is still a duration.
            duration_only = DURATION_TOKEN.match(token)
            if duration_only and "duration" not in fields:
                duration = normalise_duration(token)
                found = _from(duration, ocr_confidence=ocr_confidence)
                if found is not None:
                    fields["duration"] = found
                    position += 1
                    continue
            if BARE_NUMBER.match(token) and "strength" not in fields:
                # A number with no unit. Kept as-is; `infer_strength` decides afterwards
                # whether the medication dictionary can supply the unit, and if it cannot the
                # number stands alone — which is exactly what the prescription says.
                fields["strength"] = Field(
                    value=token, raw=token, source="bare", confidence=ocr_confidence
                )
        position += 1


def _needs_verification(medication: InterpretedMedication) -> bool:
    """Whether a human has to look at this line before it can be trusted.

    Any one of these is enough, and they are ORed rather than weighed because they are
    different kinds of doubt and a system that averages them will average one of them away:

    * the name is unresolved, or resolved only as a suggestion;
    * the recogniser was not confident about the characters;
    * the interpretation itself rests on a weak field;
    * there is no schedule at all — a medicine with no idea of when to take it is not an
      instruction a patient can follow, however well the name was read.
    """
    if medication.name_match.needs_confirmation:
        return True
    if medication.ocr_confidence <= settings.ocr_low_confidence_threshold:
        return True
    if medication.interpretation_confidence < settings.rx_interpretation_confidence_floor:
        return True
    return not medication.fields.keys() & {"frequency", "instruction", "timing"}


def interpret(result: OCRResult) -> PrescriptionReading:
    """Every line of an OCR result, read for meaning. The entry point for the pipeline."""
    reading = PrescriptionReading(raw_ocr_text=result.text, backend=result.backend)
    for page in result.pages:
        for block in page.blocks:
            medication = parse_line(
                block.text,
                ocr_confidence=block.confidence,
                page=page.page,
                engine=block.engine or result.backend,
            )
            if medication is not None:
                reading.medications.append(medication)
    return reading


def normalise_token(token: str) -> str:
    """Exposed for the eval harness, which folds gold-script tokens the same way."""
    return fold(token)
