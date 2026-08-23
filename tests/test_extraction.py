"""Phase 2 — extraction quality, and the anti-hallucination gates.

The most important test in this file is `test_hallucinated_quote_is_rejected`. It is the one
that makes the eval harness's "hallucination rate: 0" claim mean something.
"""

from __future__ import annotations

import pytest

from app.contracts.provenance import Modality
from app.core.errors import LLMContractError
from app.llm.extraction import extract
from app.llm.offline import extract_offline, match_options
from app.llm.protocol import LLMResponse, parse_or_fail
from app.llm.schemas import ExtractionResult
from app.modules.dialogue.ontology import load_ontology


@pytest.fixture
def ontology():
    return load_ontology()


class StubLLM:
    """A backend that returns exactly what a test tells it to. Not a mock of Groq — a stand-in
    for 'some model said this', which is the only thing the extraction layer may assume."""

    name = "stub-model"
    version = "test"
    offline = False

    def __init__(self, text: str) -> None:
        self.text = text

    def complete(self, *, system: str, user: str, schema_hint: str) -> LLMResponse:
        return LLMResponse(
            text=self.text,
            model_name=self.name,
            model_version=self.version,
            prompt=f"{system}\n{user}",
            offline=False,
            latency_ms=1,
        )


def _use(monkeypatch, backend) -> None:
    import app.llm.extraction as extraction_module

    monkeypatch.setattr(extraction_module, "get_llm", lambda: backend)


UTTERANCE = "mere chhaati mein bahut dard ho raha hai aur thanda paseena aa raha tha"


def test_offline_extractor_quotes_are_real_substrings(ontology) -> None:
    for qid in ("hpi.site", "hpi.associated", "pmh.conditions", "ph.tobacco"):
        result = extract_offline(ontology.by_id[qid], UTTERANCE)
        for slot in result["slots"]:
            assert slot["quote"].casefold() in UTTERANCE.casefold(), (
                f"{qid} produced a quote that is not in the utterance: {slot['quote']!r}"
            )


def test_offline_extractor_is_deterministic(ontology) -> None:
    q = ontology.by_id["hpi.site"]
    assert extract_offline(q, UTTERANCE) == extract_offline(q, UTTERANCE)


def test_hallucinated_quote_is_rejected(monkeypatch, ontology, ledger) -> None:
    """The model claims the patient mentioned crushing pain. They did not. Nothing is recorded."""
    _use(
        monkeypatch,
        StubLLM(
            '{"slots": [{"path": "hpi.character", "value": "pressure", '
            '"quote": "crushing central chest pain radiating to the arm", "confidence": 0.95}], '
            '"unplaced": []}'
        ),
    )
    outcome = extract(
        question=ontology.by_id["hpi.character"],
        utterance=UTTERANCE,
        ontology=ontology,
        ledger=ledger,
        turn_id="t1",
    )
    assert outcome.accepted == 0
    assert len(outcome.rejected_unquoted) == 1
    assert not ledger.active_facts(), "a hallucinated quote must record nothing at all"


def test_value_outside_the_option_set_is_rejected(monkeypatch, ontology, ledger) -> None:
    _use(
        monkeypatch,
        StubLLM(
            '{"slots": [{"path": "hpi.site", "value": "pancreas", '
            '"quote": "chhaati", "confidence": 0.9}], "unplaced": []}'
        ),
    )
    outcome = extract(
        question=ontology.by_id["hpi.site"],
        utterance=UTTERANCE,
        ontology=ontology,
        ledger=ledger,
        turn_id="t1",
    )
    assert outcome.accepted == 0 and outcome.rejected_bad_value


def test_unknown_path_is_rejected(monkeypatch, ontology, ledger) -> None:
    _use(
        monkeypatch,
        StubLLM(
            '{"slots": [{"path": "hpi.invented_field", "value": "chest", '
            '"quote": "chhaati", "confidence": 0.9}], "unplaced": []}'
        ),
    )
    outcome = extract(
        question=ontology.by_id["hpi.site"],
        utterance=UTTERANCE,
        ontology=ontology,
        ledger=ledger,
        turn_id="t1",
    )
    assert outcome.accepted == 0 and outcome.rejected_unknown_path == ["hpi.invented_field"]


def test_valid_extraction_is_recorded_with_the_quote_as_its_span(
    monkeypatch, ontology, ledger
) -> None:
    _use(
        monkeypatch,
        StubLLM(
            '{"slots": [{"path": "hpi.site", "value": "chest", '
            '"quote": "chhaati", "confidence": 0.86}], "unplaced": []}'
        ),
    )
    outcome = extract(
        question=ontology.by_id["hpi.site"],
        utterance=UTTERANCE,
        ontology=ontology,
        ledger=ledger,
        turn_id="t1",
    )
    assert outcome.accepted == 1
    fact = outcome.facts[0]
    assert fact.value == "chest"
    assert fact.source.verbatim == "chhaati", "the span must be the quote, not the paragraph"
    assert fact.tier.value == "stated"


def test_non_json_output_is_a_hard_failure(monkeypatch, ontology, ledger) -> None:
    """No silent fallback to free text. The extraction is lost; nothing is guessed."""
    _use(monkeypatch, StubLLM("The patient appears to have angina."))
    with pytest.raises(LLMContractError, match="not JSON"):
        extract(
            question=ontology.by_id["hpi.site"],
            utterance=UTTERANCE,
            ontology=ontology,
            ledger=ledger,
            turn_id="t1",
        )
    assert not ledger.active_facts()


def test_schema_violation_is_a_hard_failure(monkeypatch, ontology, ledger) -> None:
    _use(monkeypatch, StubLLM('{"slots": [{"path": "hpi.site", "value": "chest"}]}'))
    with pytest.raises(LLMContractError, match="does not match"):
        extract(
            question=ontology.by_id["hpi.site"],
            utterance=UTTERANCE,
            ontology=ontology,
            ledger=ledger,
            turn_id="t1",
        )


def test_fenced_json_is_unwrapped_not_repaired() -> None:
    response = LLMResponse(
        text='```json\n{"slots": [], "unplaced": []}\n```',
        model_name="m",
        model_version="v",
        prompt="p",
        offline=False,
    )
    assert parse_or_fail(response, ExtractionResult).slots == []


def test_unplaced_narration_is_kept_not_forced_into_a_slot(monkeypatch, ontology, ledger) -> None:
    _use(monkeypatch, StubLLM('{"slots": [], "unplaced": ["my son also had this last year"]}'))
    outcome = extract(
        question=ontology.by_id["hpi.site"],
        utterance=UTTERANCE,
        ontology=ontology,
        ledger=ledger,
        turn_id="t1",
    )
    assert outcome.unplaced == ["my son also had this last year"]
    assert not ledger.active_facts()


def test_asr_confidence_caps_extraction_confidence(monkeypatch, ontology, ledger) -> None:
    """A confident model reading an unreliable transcript is not a confident fact."""
    _use(
        monkeypatch,
        StubLLM(
            '{"slots": [{"path": "hpi.site", "value": "chest", '
            '"quote": "chhaati", "confidence": 0.99}], "unplaced": []}'
        ),
    )
    outcome = extract(
        question=ontology.by_id["hpi.site"],
        utterance=UTTERANCE,
        ontology=ontology,
        ledger=ledger,
        turn_id="t1",
        asr_confidence=0.55,
        modality=Modality.SPEECH,
    )
    assert outcome.facts[0].confidence == pytest.approx(0.55)


def test_negation_is_not_read_as_affirmation(ontology) -> None:
    """'nahin, main koi dawa nahin leta' is a no. Getting this wrong invents a medication."""
    result = extract_offline(ontology.by_id["med.taking"], "nahin, main koi dawa nahin leta")
    assert result["slots"][0]["value"] is False


def test_low_literacy_phrasing_reaches_the_right_option(ontology) -> None:
    cases = [
        (
            "hpi.character",
            "aisa lag raha tha jaise seene pe koi bhaari patthar rakha ho",
            "pressure",
        ),
        ("hpi.onset", "bilkul achanak shuru hua tha", "sudden"),
        ("ph.tobacco", "main gutka khata hoon din me char paanch baar", "current_chew"),
        ("ros.gi", "kala pakhana aa raha hai teen din se", "melaena"),
    ]
    for qid, utterance, expected in cases:
        hits = match_options(load_ontology().by_id[qid], utterance)
        assert hits, f"{qid}: nothing matched {utterance!r}"
        assert expected in [h[0] for h in hits], (
            f"{qid}: expected {expected}, got {[h[0] for h in hits]}"
        )
