"""Demo mode — one click, one complete synthetic session.

This is not a convenience. A jury has ninety seconds and nobody is going to tap forty-nine
answers in front of them, so without this the system's best work is unreachable in a demo.

Each case drives the **real** machinery: the same state machine, the same extraction, the same
rule engine, the same OCR pipeline. Nothing is stubbed and no output is pre-baked — a demo
case is a script of answers, played through the product. If a demo looks good here, the
product is good; that is the only kind of demo worth building.

Every case is synthetic. No real patient, no real prescription, no real clinician.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body

from app.api.deps import CurrentIdentity, DbSession, load_context, save_context
from app.audit.chain import record
from app.contracts.provenance import Modality
from app.core.config import settings
from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.modules.dialogue.answers import record_answer, record_derived
from app.modules.dialogue.voice import handle_spoken_answer
from app.modules.documents.pipeline import ingest
from app.modules.encounter import guest
from app.modules.encounter import sweep as SWEEP
from app.redflags.engine import evaluate, raise_priority
from app.speech.protocol import Transcript

log = get_logger(__name__)

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "documents"


@dataclass(frozen=True, slots=True)
class DemoCase:
    """A synthetic patient, and what the judge should watch for."""

    id: str
    title: str
    shows: str
    language: str
    ayush: bool
    #: Gold script id in eval/, so a demo case and an evaluated case are the same artefact.
    script: str
    document: str | None = None
    watch_for: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "shows": self.shows,
            "language": self.language,
            "ayush": self.ayush,
            "document": self.document,
            "watchFor": list(self.watch_for),
        }


#: Six cases, chosen so that between them they exercise every claim the product makes —
#: including the one that proves it does NOT over-alert.
CASES: tuple[DemoCase, ...] = (
    DemoCase(
        id="acute-cardiac",
        title="Chest pain, narrated in Hinglish",
        shows="Multilingual narration → structured facts → deterministic emergency escalation",
        language="hi",
        ayush=False,
        script="s30-hinglish-chest",
        watch_for=(
            "Every clinical answer arrives as Hinglish speech, not a tap.",
            "Escalates to IMMEDIATE before the interview finishes.",
            "Each summary line traces back to the patient's own words.",
        ),
    ),
    DemoCase(
        id="documents-timeline",
        title="Prior prescription becomes a timeline",
        shows="OCR → entity extraction → chronological timeline → click-to-source with a bbox",
        language="en",
        ayush=False,
        script="s22-diabetes-followup",
        document="prescription.pdf",
        watch_for=(
            "Four medications with dose and frequency, read from a PDF.",
            "Each one carries a page and a bounding box.",
        ),
    ),
    DemoCase(
        id="photo-misread",
        title="A photographed prescription, misread — and caught",
        shows="High-confidence OCR error surfaced by the verification lane, not by a threshold",
        language="en",
        ayush=False,
        script="s22-diabetes-followup",
        document="prescription_photo_handheld.jpg",
        watch_for=(
            "The paper says AMLODIPINE 5MG. OCR reads it as 'SMG' — a 5 mistaken for an S.",
            "Confidence on that line is 0.94. The engine is not hedging; it is confident "
            "and wrong, which is what a confidence threshold cannot catch.",
            "The patient sees the crop of their OWN line beside the reading, so the "
            "mismatch is visible rather than remembered — and Correct is one tap.",
            "Amlodipine 5mg and 10mg are both ordinary doses: a misread digit here is a "
            "different prescription, not a typo.",
        ),
    ),
    DemoCase(
        id="contradiction",
        title="Patient says no medicines; the prescription disagrees",
        shows="Both sources retained, neither overwritten, conflict surfaced to the physician",
        language="en",
        ayush=False,
        script="s20-routine-checkup",
        document="prescription.pdf",
        watch_for=(
            "The patient denies taking any medicine.",
            "Their own prescription lists four.",
            "The system records both and asks the physician to resolve it.",
        ),
    ),
    DemoCase(
        id="ayush",
        title="Ayurvedic intake — Dashavidha Pariksha",
        shows="AYUSH extension, derived Vaya, coded parameters, unmapped handled honestly",
        language="en",
        ayush=True,
        script="s48-ayush-vata",
        watch_for=(
            "Vaya is derived from the ABHA date of birth, never asked.",
            "Every parameter carries a retrieved code, or an honest 'unmapped'.",
        ),
    ),
    DemoCase(
        id="routine",
        title="An ordinary knee complaint",
        shows="The system does NOT over-alert: 22 rules evaluated, none fire",
        language="en",
        ayush=False,
        script="s18-knee-oa",
        watch_for=(
            "No red flag fires, and the screen says so explicitly.",
            "'No rule fired' is not the same claim as 'this patient is low risk'.",
        ),
    ),
    DemoCase(
        id="recurrence",
        title="The same complaint, a year later",
        shows=(
            "Longitudinal memory: today's visit beside a prior one, matched on features the "
            "patient actually stated at both"
        ),
        language="en",
        ayush=False,
        script="s19-acidity",
        document="prescription.pdf",
        watch_for=(
            "The demo patient already has three visits on file before this one starts.",
            "Four features overlap with the visit of 20 Aug 2025 — site, character, timing "
            "and the post-meal pattern — and each is listed rather than scored.",
            "No percentage appears anywhere: a number between two encounters reads as a "
            "probability of recurrence, and this system does not predict disease.",
            "The medicines found on the prescription stay 'documented'. Nothing concludes "
            "the patient is still taking them.",
        ),
    ),
)

CASES_BY_ID = {case.id: case for case in CASES}


def _load_script(script_id: str) -> dict[str, Any]:
    for folder in ("scripts", "holdout"):
        path = settings.path("eval") / folder / f"{script_id}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    raise ValidationError(f"Demo script {script_id!r} is missing from eval/.")


@router.get("/cases")
async def list_cases() -> dict[str, Any]:
    return {
        "cases": [case.to_dict() for case in CASES],
        "notice": (
            "Every case is synthetic and is played through the real state machine, the real "
            "extractor and the real rule engine. No output here is pre-recorded."
        ),
    }


@router.post("/cases/{case_id}/load")
async def load_case(
    db: DbSession,
    case_id: str,
    identity: CurrentIdentity,
    payload: Annotated[dict | None, Body()] = None,
) -> dict[str, Any]:
    """Play a synthetic case into an existing session, answer by answer.

    The session must already exist and hold consent — demo mode does not bypass the consent
    gate, because a demo that skips the safety machinery is not a demo of this product.
    """
    case = CASES_BY_ID.get(case_id)
    if case is None:
        raise ValidationError(f"Unknown demo case {case_id!r}. Known: {sorted(CASES_BY_ID)}.")

    session_ref = str((payload or {}).get("sessionRef") or "")
    if not session_ref:
        raise ValidationError("sessionRef is required.")

    context = await load_context(db, session_ref, identity=identity)
    script = _load_script(case.script)

    context.state.values.update(
        {f"demographics.{k}": v for k, v in (script.get("demographics") or {}).items()}
    )

    by_question = {turn["question_id"]: turn for turn in script["turns"]}
    answered = 0
    spoken = 0
    degraded = 0
    guard = 0

    while (question := context.machine.next_question()) is not None and guard < 200:
        guard += 1
        turn = by_question.get(question.question_id)
        if turn is None or turn.get("decline"):
            context.machine.decline(question.question_id)
            continue

        utterance = turn.get("utterance")
        if utterance and "voice" in context.ledger.consent_scopes:
            outcome = handle_spoken_answer(
                context.machine,
                context.ledger,
                turn_id=question.turn_id,
                question_id=question.question_id,
                transcript=Transcript(
                    text=utterance,
                    confidence=float(turn.get("asr_confidence", 0.92)),
                    language=script.get("language", "en"),
                    backend="demo",
                ),
            )
            spoken += 1
            if outcome.degraded_to_touch:
                degraded += 1
                if turn.get("tap") is None:
                    context.machine.decline(question.question_id)
                    continue
                again = context.machine.next_question()
                if again is None or again.question_id != question.question_id:
                    continue
                question = again
            else:
                answered += 1
                continue

        value = turn.get("tap")
        if value is None:
            value = utterance
        if value is None:
            context.machine.decline(question.question_id)
            continue
        record_answer(
            context.machine,
            context.ledger,
            turn_id=question.turn_id,
            question_id=question.question_id,
            value=value,
            modality=Modality.TYPED if turn.get("tap") is None else Modality.TOUCH,
            language=context.row.language,
        )
        answered += 1

    for derived_question, derived_value, _code in context.machine.derived_questions():
        record_derived(context.machine, context.ledger, derived_question, derived_value)

    document_result = None
    if case.document and "documents" in context.ledger.consent_scopes:
        path = FIXTURES / case.document
        if path.exists():
            data = path.read_bytes()
            result = ingest(
                context.ledger,
                data,
                filename=case.document,
                media_type="application/pdf",
                known_paths=context.machine.ontology.known_paths,
                backend_name="textlayer",
                sex=str(context.state.values.get("demographics.gender") or "") or None,
            )
            document_result = {
                "documentId": result.document_id,
                "factsRecorded": len(result.facts),
                "needsVerification": len(result.needs_verification),
            }
            from app.db.models import SessionDocument

            db.add(
                SessionDocument(
                    session_id=context.row.id,
                    document_id=result.document_id,
                    filename=result.filename,
                    media_type="application/pdf",
                    pages=len(result.pages),
                    ocr_backend=result.backend,
                    mean_confidence=result.mean_confidence,
                    needs_verification=bool(result.needs_verification),
                    pages_json=result.pages,
                    entities_json=[e.to_dict() for e in result.entities]
                    + result.needs_verification,
                    # The same omission as the upload route had: without the bytes the
                    # evidence drawer has nothing to draw the bounding box on, and the demo
                    # case whose whole point is "click the medicine, see the prescription"
                    # showed an empty panel.
                    content=data,
                )
            )

    escalation = evaluate(
        context.ledger,
        current_priority=context.row.priority,
        extra_values=context.state.values,
    )
    context.row.priority = raise_priority(context.row.priority, escalation.priority).label
    context.row.status = "ready_for_review"

    from app.contracts.contradictions import detect

    contradictions = detect(context.ledger)

    await record(
        db,
        actor=identity.actor,
        actor_role=identity.role,
        purpose_of_use="TREATMENT",
        action="demo.load_case",
        abha_ref=context.row.abha_ref,
        consent_ref=context.row.consent_ref,
        request_summary={"case": case_id, "script": case.script},
        response_summary={"answered": answered, "priority": context.row.priority},
    )
    await save_context(db, context)

    log.info(
        "demo.case_loaded",
        case=case_id, session=session_ref, answered=answered,
        spoken=spoken, degraded=degraded, priority=context.row.priority,
    )

    return {
        "case": case.to_dict(),
        "sessionRef": session_ref,
        "answered": answered,
        "spokenTurns": spoken,
        "degradedToTouch": degraded,
        "factsRecorded": len(context.ledger.active_facts()),
        "priority": context.row.priority,
        "redFlags": [f.rule_id for f in escalation.flags],
        "contradictions": len(contradictions),
        "document": document_result,
    }


# ──────────────────────────────────────────────── guest mode


@router.post("/guest", status_code=201)
async def start_guest(db: DbSession) -> dict[str, Any]:
    """Start a demo session. No account, no personal information, no ABHA.

    Creates a REAL patient row flagged `is_synthetic=True`, with the full seeded history —
    three dated lab reports, a prescription OCR genuinely misreads, two prior visits and a
    voice answer with a measured ASR confidence. Built by the same `seed.build_history` the
    canonical demo patient uses, so a judge sees the real pipeline rather than a lighter
    imitation of it.

    DELIBERATELY UNAUTHENTICATED. Guest mode exists so somebody can try the product without
    handing over an identity; requiring one to get in would defeat it. What keeps this safe
    is not a token but `cohort.restrict_to_cohort()`: a synthetic record cannot retrieve
    against a clinical one, or the reverse.
    """
    result = await guest.create(db)
    await db.commit()
    log.info("guest.session_started", patientRef=result["patientRef"])
    return {
        **result,
        "notice": (
            "This is a demonstration record. Every value in it is synthetic and it is kept "
            "entirely separate from any clinical data."
        ),
    }


@router.post("/guest/{patient_ref}/reset")
async def reset_guest(db: DbSession, patient_ref: str) -> dict[str, Any]:
    """Restore the demo to its starting state, in one call.

    A demo is run repeatedly in front of people and the second run starting from the first
    run's leftovers is how it goes wrong. This deletes the record and rebuilds it, and
    returns the row counts on both sides so the caller can SEE that the starting state was
    restored exactly rather than approximately.
    """
    if not guest.is_guest_ref(patient_ref):
        # Refusing by NAME SHAPE before touching the database. `reset` deletes a patient and
        # everything cascading from it; pointing it at a clinical record would be
        # catastrophic and irreversible, so the guard is the first thing that runs.
        raise ValidationError("Only a demo record can be reset.")
    result = await guest.reset(db, patient_ref)
    await db.commit()
    return result


@router.post("/guest/sweep")
async def sweep_guests(
    db: DbSession, hours: float | None = None, dry_run: bool = False
) -> dict[str, Any]:
    """Remove demo records older than the TTL, and everything attributable to them.

    Runs automatically when a new guest is created; this endpoint exists so it can be run on
    demand — before an event, or to clear a backlog. `dry_run=true` reports what WOULD go
    without touching anything, which is the only sane way to point a cascading delete at a
    production database for the first time.

    Scoped to guest records by two independent conditions inside `sweep`; a clinical record
    cannot be reached from here even if one were mislabelled.
    """
    result = await SWEEP.sweep(db, hours=hours, dry_run=dry_run)
    if not dry_run:
        await db.commit()
    return result


@router.get("/guest/orphans")
async def guest_orphans(db: DbSession) -> dict[str, Any]:
    """Capture-side rows whose owning encounter is gone. Should always be zero."""
    return {
        "orphans": await SWEEP.orphan_report(db),
        "note": (
            "consent_record, intake_session and submitted_bundle are keyed by session_ref and "
            "have no foreign key to patient, so a plain patient delete would strand them. "
            "Non-zero here means something deleted a patient without clearing them."
        ),
    }
