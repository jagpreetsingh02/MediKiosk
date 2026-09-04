"""Phase 3 — sig normalisation, constrained name matching, and the readable prescription.

The theme of this file: **the system is allowed to say "I do not know".** Most of these tests
assert that it does so, in the cases where the alternative is a confident, plausible, wrong
medicine name on a physician's screen.
"""

from __future__ import annotations

import random
import string

import pytest

from app.core.config import settings
from app.modules.documents.medications import (
    infer_strength,
    load_medications,
    match_name,
)
from app.modules.documents.prescription import interpret, parse_line
from app.modules.documents.sig import (
    interpret_schedule,
    normalise_duration,
    normalise_frequency,
    normalise_instruction,
    normalise_route,
    normalise_timing,
)

# ------------------------------------------------------------------ sig lookup


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("PCM", "Paracetamol"),  # resolved by the dictionary, not the sig table
    ],
)
def test_a_drug_abbreviation_resolves_to_the_substance(token: str, expected: str) -> None:
    match = match_name(token)
    assert match.name == expected
    assert match.status == "abbreviation"


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("BD", "twice daily"),
        ("OD", "once daily"),
        ("TDS", "three times a day"),
        ("b.d.", "twice daily"),
        ("q8h", "every 8 hours"),
    ],
)
def test_frequency_codes_come_from_the_table(token: str, expected: str) -> None:
    found = normalise_frequency(token)
    assert found is not None and found.display == expected
    assert found.source == "abbreviation"


@pytest.mark.parametrize(
    ("token", "expected"),
    [("HS", "at bedtime"), ("AC", "before food"), ("PC", "after food"), ("nocte", "at night")],
)
def test_timing_codes_come_from_the_table(token: str, expected: str) -> None:
    found = normalise_timing(token)
    assert found is not None and found.display == expected


def test_every_abbreviation_key_is_a_string() -> None:
    """YAML 1.1 reads bare ON, OFF, NO, Y, N, YES as *booleans*.

    The timing entry `ON:` therefore loaded as the key `False`, and folding a bool threw on
    the first lookup — taking the whole table with it. Asserted as a property of the file
    rather than against one entry, so it still holds after an entry is added or removed.
    """
    from app.modules.documents.sig import load_table

    table = load_table()
    for category, entries in table.items():
        if not isinstance(entries, dict) or category == "positional_slots":
            continue
        for key in entries:
            assert isinstance(key, str), f"{category}: {key!r} parsed as {type(key).__name__}"


def test_an_abbreviation_that_is_also_an_english_word_is_not_in_the_table() -> None:
    """"Sample collected on 02/02/2026" parsed as a medicine to be taken at night.

    An exact-match table cannot disambiguate a sig code from the ordinary word it collides
    with — that needs the rest of the line, which this layer deliberately does not read. The
    resolution is to leave such codes out, not to add context-sensitivity here.
    """
    from app.modules.documents.sig import load_table

    english = {"on", "no", "or", "as", "at", "in", "is", "it", "to", "do", "am", "an", "be"}
    table = load_table()
    for category in ("frequency", "instruction", "timing", "route", "form"):
        for key in table[category]:
            assert key.casefold() not in english, f"{category}: {key!r} is an English word"


def test_sos_is_not_a_frequency() -> None:
    """Rendering "as needed" as a schedule is how a rescue medicine gets taken four times
    a day. It has no times-per-day, and the table must not pretend otherwise."""
    assert normalise_frequency("SOS") is None
    instruction = normalise_instruction("SOS")
    assert instruction is not None
    assert instruction.display == "only when you need it"


@pytest.mark.parametrize(
    ("notation", "times", "contains"),
    [("1-0-1", 2, "morning"), ("1-1-1", 3, "afternoon"), ("0-0-1", 1, "night")],
)
def test_positional_notation_is_read_positionally(
    notation: str, times: int, contains: str
) -> None:
    found = normalise_frequency(notation)
    assert found is not None
    assert found.times_per_day == times
    assert contains in found.display
    assert found.source == "positional"


def test_a_stopped_medicine_is_not_given_an_invented_schedule() -> None:
    found = normalise_frequency("0-0-0")
    assert found is not None and found.times_per_day == 0
    assert "not currently" in found.display


def test_an_unknown_code_returns_nothing_rather_than_a_guess() -> None:
    """No similarity scoring lives in the sig table. Exact hit, or nothing."""
    for token in ("ZZ", "QQD", "BDD", "banana"):
        assert normalise_frequency(token) is None
        assert normalise_timing(token) is None
        assert normalise_route(token) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("5d", "5 days"), ("5 days", "5 days"), ("2wks", "2 weeks"), ("1 week", "1 week")],
)
def test_durations_normalise_and_stay_grammatical(raw: str, expected: str) -> None:
    found = normalise_duration(raw)
    assert found is not None and found.display == expected


def test_an_unknown_duration_unit_is_not_assumed_to_be_days() -> None:
    """"5 doses" and "5 days" are not interchangeable."""
    assert normalise_duration("5 doses") is None


def test_frequency_timing_and_condition_are_kept_apart() -> None:
    """"BD bf" is twice daily AND before food. One field would lose one of them."""
    schedule = interpret_schedule(["BD", "bf"])
    assert schedule.frequency is not None and schedule.frequency.display == "twice daily"
    assert schedule.timing is not None and schedule.timing.display == "before food"
    assert schedule.sentence() == "twice daily, before food"


# ------------------------------------------------------------------ name matching


def test_an_exact_name_is_returned_unchanged() -> None:
    match = match_name("Augmentin")
    assert (match.status, match.name) == ("exact", "Augmentin")
    assert match.generic == "Amoxicillin + Clavulanic acid"


def test_a_brand_keeps_its_brand_and_carries_its_generic() -> None:
    """A patient holding a strip labelled "Pantop" must not be read back "Pantoprazole"."""
    match = match_name("Pantop")
    assert match.name == "Pantop"
    assert match.brand == "Pantop"
    assert match.generic == "Pantoprazole"


def test_a_clear_misreading_is_corrected_and_says_so() -> None:
    match = match_name("Augmtin", ocr_confidence=0.9)
    assert match.status == "normalised"
    assert match.name == "Augmentin"
    assert match.needs_confirmation is False


def test_a_correction_is_never_more_confident_than_the_characters_it_corrected() -> None:
    match = match_name("Metfomin", ocr_confidence=0.7)
    assert match.status == "normalised"
    assert match.confidence <= 0.7


def test_an_ambiguous_fragment_is_offered_as_candidates_not_resolved() -> None:
    """"Amlo" is Amlodipine, Amlong or Amlokind. Picking one is not reading, it is guessing."""
    match = match_name("Amlo", ocr_confidence=0.95)
    assert match.name is None
    assert match.status == "candidate"
    assert match.needs_confirmation is True
    assert match.candidates


def test_an_illegible_name_is_never_auto_corrected_however_well_it_scores() -> None:
    """The characters it scored on are characters nobody read."""
    match = match_name("A?gm?tin", ocr_confidence=0.95)
    assert match.status == "illegible"
    assert match.name is None
    assert match.needs_confirmation is True


def test_a_strong_match_on_badly_read_characters_is_not_applied() -> None:
    """Rule 3: the OCR confidence gates the correction independently of the similarity."""
    high = match_name("Metfomin", ocr_confidence=0.9)
    low = match_name("Metfomin", ocr_confidence=0.2)
    assert high.status == "normalised"
    assert low.status == "candidate"
    assert low.name is None


def test_a_name_in_no_dictionary_is_unknown_not_the_nearest_drug() -> None:
    match = match_name("Zzzqwx", ocr_confidence=0.95)
    assert match.status == "unknown"
    assert match.name is None
    assert match.candidates == ()


def test_the_output_can_only_ever_be_a_string_from_the_dictionary() -> None:
    """Rule 1. The single most important property in this module."""
    known = set()
    for entry in load_medications():
        known.add(entry.generic)
        known.update(entry.brands)

    rng = random.Random(20260904)
    for _ in range(400):
        noise = "".join(rng.choice(string.ascii_letters) for _ in range(rng.randint(3, 14)))
        match = match_name(noise, ocr_confidence=1.0)
        assert match.name is None or match.name in known
        for candidate in match.candidates:
            assert candidate.display in known


def test_no_single_character_loss_auto_corrects_to_a_different_medicine() -> None:
    """The adversarial sweep the auto-correct threshold is calibrated against.

    Every generic and every brand in the dictionary, with one character deleted, matched at a
    realistic OCR confidence. A correction landing on a *different medicine* is the failure
    this whole module exists to prevent, so the bound asserted here is zero, not "few".

    Measured at the time of writing: 2491 mutations, 74% auto-corrected, 0 wrong.
    """
    wrong = []
    for entry in load_medications():
        for name in (entry.generic, *entry.brands):
            for position, char in enumerate(name):
                if not char.isalnum():
                    continue
                match = match_name(name[:position] + name[position + 1 :], ocr_confidence=0.9)
                if match.status == "normalised" and match.generic != entry.generic:
                    wrong.append((name, match.name))
    assert wrong == [], f"auto-corrected to a different medicine: {wrong[:5]}"


def test_a_deliberately_lowered_threshold_would_be_caught_by_that_sweep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sweep above is only a guard if it actually fails when the bar is dropped."""
    monkeypatch.setattr(settings, "rx_name_auto_similarity", 0.55)
    monkeypatch.setattr(settings, "rx_name_margin", 0.0)
    wrong = []
    for entry in load_medications():
        for name in (entry.generic, *entry.brands):
            match = match_name(name[:-3], ocr_confidence=0.9)
            if match.status == "normalised" and match.generic != entry.generic:
                wrong.append(name)
    assert wrong, "the sweep cannot detect a bad threshold, so it proves nothing"


# ------------------------------------------------------------------ strength inference


def test_a_bare_number_gains_its_unit_only_from_the_resolved_medicine() -> None:
    assert infer_strength("40", match_name("Pantop")) == ("40 mg", "dictionary")


def test_a_bare_number_stays_bare_when_the_medicine_is_unknown() -> None:
    """Inferring a unit for a drug we could not name is inferring it from nothing."""
    assert infer_strength("500", match_name("Zzzqwx")) == ("500", "ocr")


def test_a_unit_written_on_the_paper_is_never_overridden() -> None:
    assert infer_strength("650 mg", match_name("Crocin")) == ("650 mg", "ocr")


# ------------------------------------------------------------------ whole lines


def test_the_worked_example_from_the_brief() -> None:
    """Tab Augmtin 625 mg BD × 5d → Augmentin 625 mg, twice daily, for 5 days."""
    reading = parse_line("Tab Augmtin 625 mg BD x 5d", ocr_confidence=0.9)
    assert reading is not None
    readable = reading.readable()
    assert readable["name"] == "Augmentin"
    assert readable["strength"] == "625 mg"
    assert readable["frequency"] == "twice daily"
    assert readable["duration"] == "5 days"
    assert readable["form"] == "tablet"
    assert reading.needs_verification is False


def test_pcm_500_sos() -> None:
    reading = parse_line("PCM 500 sos", ocr_confidence=0.9)
    assert reading is not None
    readable = reading.readable()
    assert readable["name"] == "Paracetamol"
    assert readable["strength"] == "500 mg"
    assert readable["instruction"] == "only when you need it"
    assert readable["frequency"] is None


def test_pantop_40_od_bf() -> None:
    reading = parse_line("Pantop 40 OD bf", ocr_confidence=0.9)
    assert reading is not None
    readable = reading.readable()
    assert readable["name"] == "Pantop"
    assert readable["generic"] == "Pantoprazole"
    assert readable["strength"] == "40 mg"
    assert readable["frequency"] == "once daily"
    assert readable["timing"] == "before food"


def test_an_unreadable_name_leaves_the_name_null_and_asks_for_confirmation() -> None:
    """The second worked example. The strength is real and is kept; the name is not invented."""
    reading = parse_line("Tab A?gm?tin 625", ocr_confidence=0.6)
    assert reading is not None
    assert reading.readable()["name"] is None
    assert reading.needs_verification is True
    assert reading.interpretation_confidence == 0.0
    assert "possibly Augmentin" in reading.sentence()


def test_an_unresolved_name_scores_zero_rather_than_scoring_its_dose() -> None:
    """A line whose dose read cleanly but whose drug did not is not a 0.9 line."""
    reading = parse_line("Tab Xyzqw 200 BD", ocr_confidence=0.95)
    assert reading is not None
    assert reading.interpretation_confidence == 0.0
    assert reading.needs_verification is True


def test_a_medicine_with_no_schedule_still_needs_a_human() -> None:
    """A name and a strength with no idea of when to take it is not an instruction."""
    reading = parse_line("Tab Amlodipine 5 mg", ocr_confidence=0.98)
    assert reading is not None
    assert reading.readable()["name"] == "Amlodipine"
    assert reading.needs_verification is True


@pytest.mark.parametrize(
    "line",
    [
        "Dr. R. Sharma, MBBS MD (Gen Med)    Reg No. TN/12345",
        "Patient: [synthetic]        Age: 64 / F",
        "Date: 14/03/2026",
        "Diagnosis: Type 2 diabetes mellitus with hypertension",
        "Advice: review after one month with fasting sugar",
        "SHRI VENKATESHWARA POLYCLINIC",
        "Rx",
    ],
)
def test_page_furniture_is_not_read_as_a_medicine(line: str) -> None:
    """A prescription is mostly not medicines. A parser that finds a drug on every line
    finds four that are not there for every one that is."""
    assert parse_line(line, ocr_confidence=0.99) is None


def test_a_syrup_volume_is_a_dose_not_a_strength() -> None:
    reading = parse_line("SYP. LACTULOSE 15ML HS", ocr_confidence=0.95)
    assert reading is not None
    assert reading.readable()["dose"] == "15 ml"
    assert reading.readable()["timing"] == "at bedtime"


def test_a_route_is_read_and_named_in_words() -> None:
    reading = parse_line("Inj Ceftriaxone 1 g IV BD x 7 days", ocr_confidence=0.95)
    assert reading is not None
    readable = reading.readable()
    assert readable["name"] == "Ceftriaxone"
    assert readable["strength"] == "1 g"
    assert "vein" in str(readable["route"])
    assert readable["duration"] == "7 days"


def test_every_field_carries_its_raw_text_and_where_it_came_from() -> None:
    reading = parse_line("TAB. METFORMIN 500MG 1-0-1 x 30 days", ocr_confidence=0.99)
    assert reading is not None
    payload = reading.to_dict()
    for name, found in payload["fields"].items():
        assert found["raw"], f"{name} lost its raw text"
        assert found["source"] in {"ocr", "abbreviation", "positional", "dictionary", "bare"}
        assert 0.0 <= found["confidence"] <= 1.0
    assert payload["fields"]["frequency"]["raw"] == "1-0-1"
    assert payload["fields"]["strength"]["raw"] == "500 MG"
    assert payload["fields"]["strength"]["value"] == "500 mg"


# ------------------------------------------------------------------ whole documents


def test_the_raw_transcription_is_preserved_alongside_the_interpretation() -> None:
    """Both, always. A client rendering only the interpretation has removed the only check
    anyone has on it."""
    from pathlib import Path

    from app.modules.documents.backends import TextLayerOCR

    fixture = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "fixtures"
        / "documents"
        / "prescription.txt"
    )
    ocr = TextLayerOCR().read(fixture.read_bytes(), filename="rx.txt", media_type="text/plain")
    reading = interpret(ocr)

    assert "METFORMIN" in reading.raw_ocr_text
    assert reading.raw_ocr_text == ocr.text
    assert len(reading.medications) == 4
    assert "Metformin 500 mg" in reading.interpreted_text
    payload = reading.to_dict()
    assert set(payload) >= {"rawOcrText", "interpretedText", "medications"}


def test_a_document_with_no_medicines_interprets_to_nothing_not_to_something() -> None:
    from pathlib import Path

    from app.modules.documents.backends import TextLayerOCR

    fixture = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "fixtures"
        / "documents"
        / "lab_report.txt"
    )
    ocr = TextLayerOCR().read(fixture.read_bytes(), filename="lab.txt", media_type="text/plain")
    reading = interpret(ocr)
    assert reading.medications == []
    assert reading.interpreted_text == ""
