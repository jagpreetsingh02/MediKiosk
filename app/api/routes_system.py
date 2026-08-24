"""System surface: /about, health, audit verification, terminology, and the stub HIS."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends

from app import __version__
from app.api.deps import CurrentIdentity, DbSession, require_action
from app.audit.chain import count_events, verify_chain
from app.core.config import SUPPORTED_LANGUAGES, WHO_ATTRIBUTION, settings
from app.fhir.r4 import FHIR_VERSION
from app.llm import registry as llm_registry
from app.modules.consent.consent import load_policy as load_consent_policy
from app.modules.dialogue.ontology import load_ontology
from app.modules.documents.backends import available_backends
from app.redflags.engine import load_rules
from app.speech import registry as speech_registry

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/about")
async def about() -> dict[str, Any]:
    """Everything a demo audience should be able to check without reading the code.

    Deliberately blunt about what is mocked. A judge should not have to ask whether the ABHA
    integration is real.
    """
    ontology = load_ontology(ayush=True)
    store_kind = "unknown"
    try:
        from app.modules.consent.session import get_store

        store_kind = (await get_store()).kind
    except Exception:  # noqa: BLE001
        store_kind = "unavailable"

    return {
        "name": "MediKiosk",
        "version": __version__,
        "problemStatement": "SIH26047 — All India Institute of Ayurveda, Ministry of Ayush",
        "purpose": (
            "Produces a structured, source-linked clinical HISTORY for a physician to review. "
            "It does not diagnose, triage to a specialty, or suggest treatment."
        ),
        "invariants": {
            "1_never_diagnoses": "No endpoint returns an assessment, differential or probability.",
            "2_provenance_or_nothing": (
                "Every fact carries the verbatim utterance or document span it came from, "
                "with a tier of stated | confirmed | document. There is no fourth tier."
            ),
            "3_red_flags_are_additive": (
                "Escalation can raise a priority and can never lower one. There is no "
                "'low priority' level."
            ),
            "4_physician_commits": (
                "Nothing reaches the HIS or the ABHA record until a physician confirms."
            ),
            "5_codes_are_retrieved": (
                "Every code is read from a version-pinned CodeSystem. Unmapped is a 200."
            ),
            "6_consent_gates_and_sessions_die": (
                "Granular revocable consent; session data purged on submit and TTL expiry; "
                "every AI call written to a hash-chained audit log."
            ),
        },
        "mocked": {
            "abhaIdentity": (
                "MOCK. Locally-signed JWTs from app/auth/mock_idp.py, issuer 'mock-abdm-idp'. "
                "Not an ABDM integration. Demo OTP is 123456."
            ),
            "hisEndpoint": (
                f"Stub receiver at {settings.his_fhir_endpoint}. No hospital vendor "
                "integration, per the problem statement's scope."
            ),
            "terminology": (
                "A small hand-seeded demo subset, not the full NAMASTE release. The "
                "ingestion path is the same; the data volume is not."
            ),
            "patientData": "100% synthetic. No real patient data has ever been in this system.",
        },
        "ontology": {
            "version": ontology.version,
            "sections": len(ontology.sections),
            "questions": len(ontology.by_id),
            "redFlagRules": len(load_rules().rules),
            "consentScopes": [s.id for s in load_consent_policy().scopes],
        },
        "llm": llm_registry.describe(),
        "speech": speech_registry.describe(),
        "ocr": {"backends": available_backends(), "configured": settings.ocr_backend},
        "languages": SUPPORTED_LANGUAGES,
        "fhirVersion": FHIR_VERSION,
        "sessionStore": store_kind,
        "sessionTtlSeconds": settings.session_ttl_seconds,
        "attribution": WHO_ATTRIBUTION,
        "portedFrom": "SIH 25026 NAMASTE↔ICD-11 service — see docs/PORTED.md",
    }


@router.get("/api/v1/audit/verify", dependencies=[Depends(require_action("audit.verify"))])
async def audit_verify(db: DbSession, identity: CurrentIdentity) -> dict[str, Any]:
    """Walk the hash chain from genesis and report the first break, if any."""
    result = await verify_chain(db)
    return {**result.to_dict(), "totalEvents": await count_events(db)}


@router.get("/api/v1/terminology/search")
async def terminology_search(
    db: DbSession, term: str, system: str | None = None, limit: int = 5
) -> dict[str, Any]:
    """Look a term up. `unmapped` is a 200 with a structured body, never a guess."""
    from app.core.config import ICD_MMS_SYSTEM
    from app.terminology.sidecar import code_reported_term

    result = await code_reported_term(db, term, system=system or ICD_MMS_SYSTEM)
    return {"term": term, **result.to_dict()}


@router.get("/api/v1/sessions/{session_ref}/inspect", tags=["jury"])
async def inspect_session(
    db: DbSession, session_ref: str, identity: CurrentIdentity
) -> dict[str, Any]:
    """The jury drawer's data — the engineering a demo otherwise hides.

    Everything here is derived live. It exists because the interesting parts of this system
    are invisible in a screenshot: that the question order came from a state machine and not
    a model, that 22 rules were evaluated and 2 fired, that every fact names a source span.
    A judge should be able to see that without reading the repository.
    """
    import time

    from app.api.deps import load_context
    from app.audit.chain import verify_chain
    from app.contracts.contradictions import detect
    from app.redflags.engine import evaluate

    started = time.perf_counter()
    context = await load_context(db, session_ref, identity=identity)
    facts = context.ledger.active_facts()
    escalation = evaluate(
        context.ledger,
        current_priority=context.row.priority,
        extra_values=context.state.values,
    )
    question = context.machine.next_question()
    chain = await verify_chain(db)

    tiers: dict[str, int] = {}
    for fact in facts:
        tiers[fact.tier.value] = tiers.get(fact.tier.value, 0) + 1

    return {
        "sessionRef": session_ref,
        "stateMachine": {
            "currentNode": question.question_id if question else "complete",
            "currentSection": question.section_id if question else None,
            "turnsTaken": len(context.state.turns),
            "askable": context.machine.progress()["askable"],
            "declined": len(context.state.declined),
            "degradedToTouch": len(context.state.forced_touch),
            "note": "Question order comes from data/ontology/*.yaml. No model is consulted.",
        },
        "facts": {
            "active": len(facts),
            "superseded": len(context.ledger.facts) - len(facts),
            "byTier": tiers,
            "withoutSource": sum(
                1 for f in context.ledger.facts if not f.source.verbatim.strip()
            ),
            "absences": len(context.ledger.absences),
        },
        "redFlags": {
            "rulesEvaluated": len(escalation.proposals),
            "fired": [f.rule_id for f in escalation.flags],
            "priority": escalation.priority.label,
            "note": "Deterministic. An LLM may propose; these rules decide.",
        },
        "contradictions": len(detect(context.ledger)),
        "consent": {
            "scopes": sorted(context.ledger.consent_scopes),
            "ref": context.row.consent_ref,
        },
        "backends": {
            "llm": llm_registry.describe(),
            "speech": speech_registry.describe(),
            "ocr": settings.ocr_backend,
        },
        "audit": {"intact": chain.intact, "events": chain.checked},
        "inspectLatencyMs": int((time.perf_counter() - started) * 1000),
    }


stub_router = APIRouter(prefix="/api/v1/stub-his", tags=["stub-his"])

#: What the stub receiver has accepted, so a demo can show the push actually landing.
_RECEIVED: list[dict[str, Any]] = []


@stub_router.post("/Bundle", status_code=201)
async def receive_bundle(payload: Annotated[dict, Body()]) -> dict[str, Any]:
    """A documented FHIR endpoint standing in for a hospital HIS. Explicitly a stub."""
    entries = payload.get("entry", [])
    record_summary = {
        "bundleId": (payload.get("identifier") or {}).get("value"),
        "type": payload.get("type"),
        "entries": len(entries),
        "resourceTypes": sorted({e.get("resource", {}).get("resourceType", "?") for e in entries}),
        "fhirVersion": payload.get("_fhirVersion"),
    }
    _RECEIVED.append(record_summary)
    return {
        "received": True,
        "warning": "STUB RECEIVER — this is not a hospital HIS.",
        **record_summary,
    }


@stub_router.get("/received")
async def received() -> dict[str, Any]:
    return {"count": len(_RECEIVED), "bundles": _RECEIVED[-20:]}
