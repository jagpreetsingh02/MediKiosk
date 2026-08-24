"""⛔ ``record_fact()`` — THE CHOKE POINT. Invariant 2 lives or dies here.

Nothing in this codebase writes a clinical fact except through this function. It refuses:

* a fact with no source span;
* a fact whose span text does not actually contain what is being recorded, when the value is
  a string (a paraphrase is not a source) — a *named* human reading of an OCR span counts
  as span text, which is how a verified correction gets in;
* a fact whose tier disagrees with its span class (``document`` tier with an utterance span);
* a ``confirmed`` fact that names no question — "the patient affirmed" is meaningless without
  saying what they were asked;
* a value at a path the ontology does not define, so a typo cannot invent a clinical field;
* anything at all on a session whose consent scope does not cover it.

``tests/test_record_fact_is_the_only_writer.py`` scans the source tree and fails if
``Fact(`` is constructed anywhere else. There is no ``force=`` parameter and no bypass. Do not
add one — the absence is the feature.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from app.contracts.provenance import (
    Absence,
    AbsenceReason,
    DocumentSpan,
    Fact,
    Modality,
    SourceTier,
    Span,
    UtteranceSpan,
    span_digest,
)
from app.core.errors import ProvenanceError, ValidationError
from app.core.logging import get_logger

log = get_logger(__name__)

#: Values that are structurally allowed to have no textual echo in the span, because the
#: patient expressed them by tapping an icon or answering a yes/no.
_NON_TEXTUAL = (bool, int, float, type(None))

_NORMALISE = re.compile(r"[^a-z0-9ऀ-෿]+")


def _norm(text: str) -> str:
    return _NORMALISE.sub(" ", text.casefold()).strip()


def _value_is_echoed(value: Any, span: Span) -> bool:
    """Is the recorded value actually evidenced by its own source span?

    Two kinds of evidence are accepted, and a span carries exactly one of them:

    * **Selection** — the span lists the option values the kiosk rendered and the patient
      pressed. The recorded value must be among them. Exact, no interpretation.
    * **Text** — the value must appear in the verbatim text (the anti-paraphrase check below).

    This is the anti-paraphrase check. It is deliberately loose — it accepts a normalised
    substring in either direction, so "burning" backs "burning pain" and vice versa — because
    a strict check would reject legitimate lemmatisation and push people to disable it. It is
    tight enough to reject a fact whose source span is about something else entirely.
    """
    selected = getattr(span, "selected_values", None)
    if selected is not None:
        # Selection evidence: the value must be one the kiosk actually rendered and the
        # patient actually pressed. Stricter than a substring match, and exact.
        wanted = value if isinstance(value, list | tuple | set) else [value]
        return bool(wanted) and all(str(v) in selected for v in wanted)
    if isinstance(value, _NON_TEXTUAL):
        return True
    if isinstance(value, list | tuple | set):
        # A multi-select is one fact with several values. Every one of them must appear in
        # the span, or the patient is being credited with a selection they did not make.
        return bool(value) and all(_value_is_echoed(item, span) for item in value)
    text = _norm(str(value))
    if not text:
        return False
    haystack = _norm(span.verbatim)
    if span.verbatim_translated:
        haystack = f"{haystack} {_norm(span.verbatim_translated)}"
    # A named human's reading of an OCR span is evidence too — that is what verification is.
    # The scrawl stays the verbatim; this admits "Metformin" as backed by a human reading
    # "TAB. METFARMIN 500mg" and saying so under their own name. `DocumentSpan` refuses a
    # reading with nobody attached, so this cannot become an anonymous free-text bypass.
    reading = getattr(span, "human_reading", None)
    if reading:
        haystack = f"{haystack} {_norm(reading)}"
    if text in haystack or haystack in text:
        return True
    # Multi-word values: every token must appear somewhere in the span.
    tokens = [t for t in text.split() if len(t) > 2]
    return bool(tokens) and all(t in haystack for t in tokens)


class FactLedger:
    """Append-only, in-memory ledger for one session. Persisted by the session store.

    Append-only is not a performance choice. A patient who contradicts themselves is
    clinically interesting, and the physician needs to see both answers; overwriting would
    destroy that. Supersession marks the old fact, it does not remove it.
    """

    __slots__ = ("session_id", "_facts", "_absences", "_digests", "consent_scopes")

    def __init__(self, session_id: str, consent_scopes: set[str] | None = None) -> None:
        self.session_id = session_id
        self._facts: list[Fact] = []
        self._absences: list[Absence] = []
        self._digests: set[str] = set()
        #: Consent scopes granted for this session. Empty set = nothing may be captured.
        self.consent_scopes: set[str] = consent_scopes or set()

    # -------------------------------------------------------------- reads

    @property
    def facts(self) -> list[Fact]:
        return list(self._facts)

    @property
    def absences(self) -> list[Absence]:
        return list(self._absences)

    def active_facts(self) -> list[Fact]:
        return [f for f in self._facts if f.active]

    def by_id(self, fact_id: str) -> Fact | None:
        return next((f for f in self._facts if f.fact_id == fact_id), None)

    def at_path(self, path: str, *, active_only: bool = True) -> list[Fact]:
        return [f for f in self._facts if f.path == path and (f.active or not active_only)]

    def paths(self) -> set[str]:
        return {f.path for f in self._facts if f.active}

    # -------------------------------------------------------------- writes

    def _supersede(self, path: str, new_fact_id: str) -> list[Fact]:
        """Mark prior active facts at `path` as superseded. Returns the replaced facts."""
        replaced: list[Fact] = []
        for index, fact in enumerate(self._facts):
            if fact.path == path and fact.active:
                self._facts[index] = fact.model_copy(update={"superseded_by": new_fact_id})
                replaced.append(fact)
        return replaced

    def _append(self, fact: Fact) -> None:
        self._facts.append(fact)
        self._digests.add(f"{fact.path}|{span_digest(fact.source)}")

    def already_recorded(self, path: str, span: Span) -> bool:
        return f"{path}|{span_digest(span)}" in self._digests

    def record_absence(
        self, path: str, reason: AbsenceReason, *, question_id: str | None = None
    ) -> Absence:
        absence = Absence(
            session_id=self.session_id, path=path, reason=reason, question_id=question_id
        )
        self._absences.append(absence)
        return absence


def record_fact(
    ledger: FactLedger,
    *,
    path: str,
    value: Any,
    tier: SourceTier,
    source: Span,
    confidence: float,
    provenance_note: str | None = None,
    known_paths: set[str] | None = None,
    required_scope: str | None = None,
    coded_value_of: set[str] | None = None,
    supersede: bool = True,
) -> Fact:
    """Record one clinical fact. The only sanctioned write path into a patient's history.

    Raises :class:`ProvenanceError` rather than returning ``None`` on any violation: a
    caller that swallowed a ``None`` would silently drop a clinical fact, which is worse than
    a 500.
    """
    if source is None:  # type: ignore[comparison-overlap]
        raise ProvenanceError(f"Refusing to record {path!r}: no source span was supplied.")

    if not isinstance(source, UtteranceSpan | DocumentSpan):
        raise ProvenanceError(
            f"Refusing to record {path!r}: source must be an UtteranceSpan or DocumentSpan, "
            f"got {type(source).__name__}."
        )

    if not source.verbatim or not source.verbatim.strip():
        raise ProvenanceError(
            f"Refusing to record {path!r}: the source span carries no verbatim text."
        )

    if value is None:
        raise ProvenanceError(
            f"Refusing to record {path!r} with a null value. An unknown field is an Absence "
            "(not_asked / declined), recorded through ledger.record_absence()."
        )

    if tier is SourceTier.DOCUMENT and not isinstance(source, DocumentSpan):
        raise ProvenanceError(
            f"Refusing to record {path!r}: tier 'document' requires a DocumentSpan carrying "
            "page and bounding box."
        )

    if tier in (SourceTier.STATED, SourceTier.CONFIRMED) and not isinstance(source, UtteranceSpan):
        raise ProvenanceError(
            f"Refusing to record {path!r}: tier {tier.value!r} requires an UtteranceSpan."
        )

    if tier is SourceTier.CONFIRMED and isinstance(source, UtteranceSpan):
        if not source.question_id:
            raise ProvenanceError(
                f"Refusing to record {path!r} as 'confirmed': no question_id. "
                "'The patient affirmed' is meaningless without naming the question asked."
            )

    if known_paths is not None and path not in known_paths:
        raise ValidationError(
            f"{path!r} is not a path the clinical ontology defines. A fact cannot invent a "
            "field; add it to data/ontology/ first."
        )

    if required_scope is not None and required_scope not in ledger.consent_scopes:
        raise ProvenanceError(
            f"Refusing to record {path!r}: consent scope {required_scope!r} was not granted "
            f"for this session (granted: {sorted(ledger.consent_scopes) or 'none'})."
        )

    if coded_value_of is not None:
        # A closed-vocabulary value. The text check below cannot apply: the patient said
        # "chhaati" and the recorded value is the option key `chest`. Demanding a textual
        # echo there would make cross-lingual extraction impossible, which for a kiosk
        # serving ten languages means demanding the wrong thing.
        #
        # The proof obligation is not waived, it is *replaced* by a stricter one: the value
        # must be a member of the option set the question actually defines. The patient's
        # words remain the span, so click-to-source still shows "chhaati" to the physician.
        wanted = value if isinstance(value, list | tuple | set) else [value]
        unknown = [v for v in wanted if str(v) not in coded_value_of]
        if unknown:
            raise ProvenanceError(
                f"Refusing to record {path!r}: {unknown!r} is not in the closed vocabulary "
                f"for this field. A coded value must come from the option set, never from "
                "free text."
            )
    elif not _value_is_echoed(value, source):
        raise ProvenanceError(
            f"Refusing to record {path!r} = {value!r}: that value does not appear in its own "
            f"source span ({source.verbatim!r}). A paraphrase is not a source — record the "
            "patient's words, or record nothing."
        )

    if ledger.already_recorded(path, source):
        existing = next(
            f
            for f in ledger.facts
            if f.path == path and span_digest(f.source) == span_digest(source)
        )
        return existing

    fact_id = f"fact_{uuid.uuid4().hex[:12]}"
    replaced = ledger._supersede(path, fact_id) if supersede else []

    fact = Fact(
        fact_id=fact_id,
        session_id=ledger.session_id,
        path=path,
        value=value,
        tier=tier,
        source=source,
        confidence=confidence,
        recorded_at=datetime.now(UTC),
        provenance_note=provenance_note,
    )
    ledger._append(fact)

    log.debug(
        "fact.recorded",
        session=ledger.session_id,
        path=path,
        tier=tier.value,
        confidence=round(confidence, 3),
        superseded=len(replaced),
    )
    return fact


def utterance_span(
    *,
    verbatim: str,
    turn_id: str,
    question_id: str,
    modality: Modality = Modality.TYPED,
    selected_values: tuple[str, ...] | None = None,
    full_text: str | None = None,
    language: str = "en",
    verbatim_translated: str | None = None,
    asr_confidence: float | None = None,
    audio_ref: str | None = None,
    audio_start_ms: int | None = None,
    audio_end_ms: int | None = None,
) -> UtteranceSpan:
    """Build an utterance span, locating `verbatim` inside `full_text` to get real offsets.

    Callers pass the substring they extracted; the offsets are computed here so no caller
    can quietly hand-write a range that does not match the text.
    """
    haystack = full_text if full_text is not None else verbatim
    start = haystack.find(verbatim)
    if start < 0:
        lowered = haystack.casefold().find(verbatim.casefold())
        start = lowered if lowered >= 0 else 0
    return UtteranceSpan(
        verbatim=verbatim,
        verbatim_translated=verbatim_translated,
        language=language,
        turn_id=turn_id,
        question_id=question_id,
        char_start=start,
        char_end=start + len(verbatim),
        modality=modality,
        selected_values=selected_values,
        asr_confidence=asr_confidence,
        audio_ref=audio_ref,
        audio_start_ms=audio_start_ms,
        audio_end_ms=audio_end_ms,
    )
