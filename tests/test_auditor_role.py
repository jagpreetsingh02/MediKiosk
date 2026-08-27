"""The auditor role is structurally unable to write anything.

⛔ THE PROOF IS AT THE ROLE LEVEL, NOT THE ROUTE LEVEL. Checking that `routes_audit.py`
contains no POST is necessary but not sufficient — nothing stops a future PR adding a mutating
route gated by an action `auditor` already happens to hold. So this scans EVERY router in
`app/api/`, collects the action string behind every mutating route (POST/PUT/PATCH/DELETE),
and asserts the auditor's action set from `config/policy.yaml` has zero overlap with it. That
claim survives a new route being added anywhere, by anyone, as long as the policy file is
still the source of truth for what the role can do — which is the whole architecture.

The live example alongside it (attempting the physician commit route with an auditor token)
is not redundant with the structural test: it proves the STRUCTURAL claim is also true at
RUNTIME — that `require_action` actually enforces what the policy file says, not merely that
the policy file looks right on paper.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

from app.audit.chain import count_events, record
from app.audit.review import (
    ABSENCE_OK_WITHOUT_EVIDENCE,
    no_assessment_claim_check,
    provenance_completeness,
    tamper_demonstration,
)
from app.db.durable import ClinicalFactRecord, Encounter, Patient, SourceEvidence
from tests.test_authorization import client  # noqa: F401 — cross-module fixture import

APP = Path(__file__).resolve().parents[1] / "app"
POLICY = Path(__file__).resolve().parents[1] / "config" / "policy.yaml"

MUTATING_METHODS = {"post", "put", "patch", "delete"}


def _required_actions_on_mutating_routes() -> set[str]:
    """Every action string gating a POST/PUT/PATCH/DELETE route, anywhere in app/api/."""
    actions: set[str] = set()
    for path in sorted((APP / "api").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            callee = node.func
            method = getattr(callee, "attr", None)
            if method not in MUTATING_METHODS:
                continue
            is_router_call = (
                isinstance(callee, ast.Attribute) and getattr(callee.value, "id", "") == "router"
            )
            if not is_router_call:
                continue
            # Walk the whole call (including its `dependencies=[...]` kwarg) for
            # require_action("x") / require_any_action("x", "y") calls anywhere inside it.
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                    if sub.func.id in ("require_action", "require_any_action"):
                        for arg in sub.args:
                            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                actions.add(arg.value)
    return actions


def _auditor_actions() -> set[str]:
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    return set(policy["roles"]["auditor"]["actions"])


def test_the_auditor_role_holds_no_mutating_action() -> None:
    """The structural claim: zero overlap between what auditor can do and what writes."""
    mutating = _required_actions_on_mutating_routes()
    auditor = _auditor_actions()

    # A scan that found nothing would pass vacuously — confirm it actually saw the API
    # before trusting an empty intersection.
    assert mutating, "the source scan found no mutating routes at all — check the AST match"

    overlap = mutating & auditor
    assert not overlap, (
        f"the auditor role can reach a mutating route via: {sorted(overlap)}. "
        "config/policy.yaml must not grant these actions to 'auditor'."
    )


def test_auditor_actions_are_all_read_shaped() -> None:
    """Every action name granted to auditor should itself read as a read, not a verb of harm."""
    for action in _auditor_actions():
        verb = action.split(".")[-1]
        assert verb in ("read", "verify", "about"), (
            f"auditor holds {action!r}, which does not read as read-only on its face"
        )


async def test_an_auditor_token_is_refused_the_commit_route(client) -> None:  # noqa: F811
    """The live proof: `require_action` actually enforces this at runtime, not just on paper."""
    token_resp = await client.post(
        "/mock-idp/token", json={"role": "auditor", "sub": "auditor@example.org"}
    )
    assert token_resp.status_code == 200
    token = token_resp.json()["access_token"]

    resp = await client.post(
        "/api/v1/sessions/sess_does_not_exist/commit",
        json={"confirmed": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, (
        f"an auditor token reached the commit route: HTTP {resp.status_code}"
    )


async def test_an_auditor_token_can_read_audit_verify(client) -> None:  # noqa: F811
    """The role is not merely refused everything — it can do the one thing it exists for.

    `purpose=RESEARCH` is required and is not incidental to this test: `auditor` is scoped to
    `purposes: [RESEARCH, STATISTICS]` in policy.yaml and every action dependency also checks
    purpose-of-use, which defaults to TREATMENT when unspecified. An auditor calling without
    naming a purpose is refused for that reason alone — found by this test failing with a 403
    whose detail named the real cause ("may not act with purpose-of-use TREATMENT") rather
    than by reading the policy file first.
    """
    token = (
        await client.post(
            "/mock-idp/token", json={"role": "auditor", "sub": "auditor@example.org"}
        )
    ).json()["access_token"]
    resp = await client.get(
        "/api/v1/audit/verify?purpose=RESEARCH",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "intact" in resp.json()


# ──────────────────────────────────────────────── provenance completeness


async def _encounter_with_facts(db, *, evidenced: int, absent: int, orphan: int = 0) -> Encounter:
    patient = Patient(patient_ref="pat_audit1", abha_ref="abha:audit1", display_name="X",
                       year_of_birth=1970, is_synthetic=False)
    db.add(patient)
    await db.flush()
    when = datetime(2026, 1, 1, tzinfo=UTC)
    encounter = Encounter(
        encounter_ref="enc_audit1", patient_id=patient.id, occurred_at=when,
        kind="intake", confirmed_by="dr.t", confirmed_at=when,
    )
    db.add(encounter)
    await db.flush()

    n = 0
    for _ in range(evidenced):
        n += 1
        f = ClinicalFactRecord(
            encounter_id=encounter.id, fact_ref=f"fact_{n}", path=f"p.{n}",
            value_json={"v": "x"}, display_value="x", tier="confirmed", state="confirmed",
            confidence=1.0, recorded_at=when, valid_from=when,
        )
        db.add(f)
        await db.flush()
        db.add(SourceEvidence(fact_id=f.id, source_type="utterance", verbatim="x",
                              language="en", modality="touch"))
    for _ in range(absent):
        n += 1
        db.add(ClinicalFactRecord(
            encounter_id=encounter.id, fact_ref=f"fact_{n}", path=f"p.{n}",
            value_json={"v": None}, display_value=None, tier="stated", state="declined",
            confidence=1.0, recorded_at=when, valid_from=when,
        ))
    for _ in range(orphan):
        n += 1
        db.add(ClinicalFactRecord(
            encounter_id=encounter.id, fact_ref=f"fact_{n}", path=f"p.{n}",
            value_json={"v": "y"}, display_value="y", tier="stated", state="stated",
            confidence=1.0, recorded_at=when, valid_from=when,
        ))
    await db.flush()
    return encounter


async def test_evidenced_and_absent_facts_are_both_complete(db_session) -> None:
    enc = await _encounter_with_facts(db_session, evidenced=3, absent=2)
    result = await provenance_completeness(db_session, enc)
    assert result["totalFacts"] == 5
    assert result["withEvidence"] == 3
    assert result["withExplicitAbsence"] == 2
    assert result["complete"] is True
    assert result["offenders"] == []


async def test_a_fact_with_neither_evidence_nor_an_absence_state_is_an_offender(db_session) -> None:
    enc = await _encounter_with_facts(db_session, evidenced=2, absent=1, orphan=1)
    result = await provenance_completeness(db_session, enc)
    assert result["complete"] is False
    assert len(result["offenders"]) == 1
    assert result["offenders"][0]["path"] == "p.4"


def test_absence_states_match_the_briefs_own_definition() -> None:
    """One definition of 'a fact may lack evidence', not two that could drift apart."""
    from app.modules.report.brief import ABSENCE_STATES

    assert set(ABSENCE_STATES) <= set(ABSENCE_OK_WITHOUT_EVIDENCE)
    assert "not_asked" in ABSENCE_OK_WITHOUT_EVIDENCE


# ──────────────────────────────────────────────── no-assessment claim


async def test_a_clean_report_passes_the_claim_check() -> None:
    result = await no_assessment_claim_check({"hpi": {"site": "chest"}, "sessionId": "s1"})
    assert result["clean"] is True
    assert result["offenders"] == []


async def test_an_assessment_shaped_field_is_caught() -> None:
    result = await no_assessment_claim_check({"extras": [{"differential": ["angina"]}]})
    assert result["clean"] is False
    assert result["offenders"][0]["field"] == "differential"


# ──────────────────────────────────────────────── tamper demonstration


@pytest.fixture
async def audit_log(db_session):
    for i in range(3):
        await record(
            db_session, actor=f"actor{i}", actor_role="clinician", purpose_of_use="TREATMENT",
            action=f"action.{i}", request_summary={"n": i},
        )
    return db_session


async def test_tamper_demo_detects_the_break(audit_log) -> None:
    result = await tamper_demonstration(audit_log)
    d = result.to_dict()
    assert d["available"] is True
    assert d["eventsInDemo"] == 3
    assert d["detected"] is True
    assert d["firstBrokenIndex"] is not None
    assert d["originalValue"] != d["corruptedValue"]


async def test_the_tamper_demo_never_touches_the_real_table(audit_log) -> None:
    """⛔ THE ONE THAT MATTERS. Byte-identical before and after, or this is not a demo."""
    from app.db.models import AuditEvent

    def snapshot(rows):
        return [(r.id, r.hash, r.prev_hash, r.action) for r in rows]

    rows_before = (await audit_log.execute(select(AuditEvent))).scalars().all()
    before = snapshot(rows_before)
    count_before = await count_events(audit_log)

    await tamper_demonstration(audit_log)

    rows_after = (await audit_log.execute(select(AuditEvent))).scalars().all()
    after = snapshot(rows_after)
    count_after = await count_events(audit_log)

    assert count_before == count_after
    assert before == after, "the tamper demo mutated the real audit_event rows"


async def test_too_few_events_reports_unavailable_rather_than_fabricating(db_session) -> None:
    result = (await tamper_demonstration(db_session)).to_dict()
    assert result["available"] is False
    assert result["detected"] is False
