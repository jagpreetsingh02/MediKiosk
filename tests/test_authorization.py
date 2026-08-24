"""Session ownership — Invariant 6's other half, and the gap this slice closed.

Before `load_context()` took an identity, a session reference in a URL was the only thing
standing between one patient and another patient's answers. Every route loaded the session by
reference and asked nobody's permission. These tests hold that shut from two directions: over
HTTP, and by scanning the source for a call site that forgot.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

pytest_plugins = []

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ----------------------------------------------------------------- the scan
#
# Same treatment `record_fact()` gets in test_invariant_provenance.py: the guarantee is only
# worth anything if it cannot be routed around by a new caller next month.


def test_no_call_site_loads_a_session_without_an_identity() -> None:
    offenders: list[str] = []
    call = re.compile(r"load_context\(\s*db,\s*session_ref\s*(?:,\s*[^)]*)?\)", re.S)
    for path in sorted((PROJECT_ROOT / "app").rglob("*.py")):
        source = path.read_text()
        for match in call.finditer(source):
            if "identity=" not in match.group(0):
                line = source[: match.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{line}")
    assert not offenders, (
        "load_context() must be given the caller's identity so it can refuse a session that "
        "is not theirs. Offending call sites:\n  " + "\n  ".join(offenders)
    )


def test_load_context_has_no_default_identity() -> None:
    """A default would be a bypass, and a bypass is the whole bug."""
    import inspect

    from app.api.deps import load_context

    parameter = inspect.signature(load_context).parameters["identity"]
    assert parameter.default is inspect.Parameter.empty
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


# ------------------------------------------------------------------ the unit


def _session_row(abha_ref: str | None):
    from app.db.models import IntakeSession

    return IntakeSession(session_ref="sess_x", abha_ref=abha_ref, status="in_progress")


def test_a_patient_reaches_their_own_session() -> None:
    from app.api.deps import assert_session_access
    from app.auth.identity import Identity

    assert_session_access(
        _session_row("abha_kamala"),
        Identity(actor="kamala", role="patient", abha_ref="abha_kamala"),
    )


def test_a_patient_is_refused_another_patients_session() -> None:
    from app.api.deps import assert_session_access
    from app.auth.identity import Identity
    from app.core.errors import PolicyDenied

    with pytest.raises(PolicyDenied, match="another patient"):
        assert_session_access(
            _session_row("abha_kamala"),
            Identity(actor="ravi", role="patient", abha_ref="abha_ravi"),
        )


def test_a_patient_token_with_no_abha_reference_reaches_nothing() -> None:
    """A token that names no patient cannot own a session, however friendly it looks."""
    from app.api.deps import assert_session_access
    from app.auth.identity import Identity
    from app.core.errors import PolicyDenied

    with pytest.raises(PolicyDenied):
        assert_session_access(
            _session_row("abha_kamala"), Identity(actor="nobody", role="patient")
        )
    with pytest.raises(PolicyDenied):
        assert_session_access(_session_row(None), Identity(actor="nobody", role="patient"))


def test_a_clinician_reaches_a_session_they_did_not_create() -> None:
    """Reviewing the queue is the job. ABAC actions constrain staff, not ownership."""
    from app.api.deps import assert_session_access
    from app.auth.identity import Identity

    assert_session_access(
        _session_row("abha_kamala"), Identity(actor="dr.mehta", role="clinician")
    )


def test_anonymous_is_refused_once_auth_is_required(monkeypatch) -> None:
    """The demo exemption is exactly that: an exemption, switched off by AUTH_REQUIRED."""
    import app.api.deps as deps
    from app.auth.identity import ANONYMOUS
    from app.core.errors import PolicyDenied

    assert_row = _session_row("abha_kamala")
    deps.assert_session_access(assert_row, ANONYMOUS)  # demo default: allowed

    monkeypatch.setattr(deps.settings, "auth_required", True)
    with pytest.raises(PolicyDenied):
        deps.assert_session_access(assert_row, ANONYMOUS)


# ------------------------------------------------------------------ over HTTP


@pytest.fixture
async def client(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("LLM_BACKEND", "offline")
    monkeypatch.setenv("SESSION_STORE_ALLOW_MEMORY_FALLBACK", "true")

    import importlib

    import app.core.config as config_module
    import app.db.session as db_module
    from app.modules.consent.session import reset_store

    config_module.get_settings.cache_clear()
    fresh = config_module.Settings()
    monkeypatch.setattr(config_module, "settings", fresh)
    for module in (
        "app.db.session",
        "app.terminology.store",
        "app.modules.consent.session",
        "app.modules.dialogue.ontology",
        "app.api.deps",
        "app.main",
    ):
        mod = importlib.import_module(module)
        if hasattr(mod, "settings"):
            monkeypatch.setattr(mod, "settings", fresh, raising=False)

    db_module.get_engine.cache_clear()
    db_module.get_sessionmaker.cache_clear()
    reset_store()

    from app.main import app

    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
        app.router.lifespan_context(app),
    ):
        yield http

    db_module.get_engine.cache_clear()
    db_module.get_sessionmaker.cache_clear()
    reset_store()
    config_module.get_settings.cache_clear()


async def _login(client, abha_address: str) -> str:
    await client.post("/mock-idp/abha/request-otp", json={"abha_address": abha_address})
    response = await client.post(
        "/mock-idp/abha/verify-otp", json={"abha_address": abha_address, "otp": "123456"}
    )
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _start_session(client, token: str) -> str:
    response = await client.post(
        "/api/v1/sessions",
        headers=_auth(token),
        json={
            "language": "en",
            "consentScopes": ["history", "voice", "documents"],
            "audioExplained": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["sessionRef"]


async def test_one_patient_cannot_read_another_patients_session(client) -> None:
    kamala = await _login(client, "kamala.devi@abdm")
    ravi = await _login(client, "demo@abdm")
    session_ref = await _start_session(client, kamala)

    mine = await client.get(f"/api/v1/sessions/{session_ref}", headers=_auth(kamala))
    assert mine.status_code == 200

    theirs = await client.get(f"/api/v1/sessions/{session_ref}", headers=_auth(ravi))
    assert theirs.status_code == 403, theirs.text
    assert "another patient" in theirs.text


async def test_one_patient_cannot_answer_into_another_patients_session(client) -> None:
    """Reading is the obvious hole. Writing into someone else's history is the worse one."""
    kamala = await _login(client, "kamala.devi@abdm")
    ravi = await _login(client, "demo@abdm")
    session_ref = await _start_session(client, kamala)

    blocked = await client.get(
        f"/api/v1/sessions/{session_ref}/dialogue/next", headers=_auth(ravi)
    )
    assert blocked.status_code == 403

    step = (
        await client.get(f"/api/v1/sessions/{session_ref}/dialogue/next", headers=_auth(kamala))
    ).json()
    answer = await client.post(
        f"/api/v1/sessions/{session_ref}/dialogue/answer",
        headers=_auth(ravi),
        json={
            "questionId": step["question"]["questionId"],
            "turnId": step["question"]["turnId"],
            "value": "chest",
        },
    )
    assert answer.status_code == 403


async def test_one_patient_cannot_upload_into_another_patients_session(client) -> None:
    kamala = await _login(client, "kamala.devi@abdm")
    ravi = await _login(client, "demo@abdm")
    session_ref = await _start_session(client, kamala)

    fixture = PROJECT_ROOT / "data" / "fixtures" / "documents"
    candidates = sorted(fixture.glob("*.pdf")) + sorted(fixture.glob("*.png"))
    assert candidates, "no document fixture to upload"
    blocked = await client.post(
        f"/api/v1/sessions/{session_ref}/documents",
        headers=_auth(ravi),
        files={"file": (candidates[0].name, candidates[0].read_bytes(), "application/pdf")},
    )
    assert blocked.status_code == 403


async def test_a_clinician_may_open_a_session_they_did_not_create(client) -> None:
    kamala = await _login(client, "kamala.devi@abdm")
    session_ref = await _start_session(client, kamala)
    clinician = (
        await client.post("/mock-idp/token", json={"role": "clinician", "sub": "dr.mehta@aiia"})
    ).json()["access_token"]

    allowed = await client.get(f"/api/v1/sessions/{session_ref}", headers=_auth(clinician))
    assert allowed.status_code == 200


async def test_the_patient_context_route_refuses_a_patient_token(client) -> None:
    """A patient may read their own record through /patients/me. The physician bridge is a
    clinician surface: it carries reconciliation findings and prior-visit detail written for
    a reader who can act on them."""
    kamala = await _login(client, "kamala.devi@abdm")
    session_ref = await _start_session(client, kamala)

    refused = await client.get(
        f"/api/v1/sessions/{session_ref}/patient-context", headers=_auth(kamala)
    )
    assert refused.status_code == 403


async def test_the_patient_context_route_resolves_history_for_a_clinician(client) -> None:
    demo = await _login(client, "demo@abdm")
    session_ref = await _start_session(client, demo)
    clinician = (
        await client.post("/mock-idp/token", json={"role": "clinician", "sub": "dr.mehta@aiia"})
    ).json()["access_token"]

    body = (
        await client.get(
            f"/api/v1/sessions/{session_ref}/patient-context", headers=_auth(clinician)
        )
    ).json()
    assert body["known"] is True, "the seeded demo patient joins to this login by ABHA ref"
    assert body["overview"]["counts"]["encounters"] >= 2
    assert body["timeline"], "the timeline must span the patient's prior encounters"
    assert body["medications"]


async def test_an_unknown_patient_is_a_normal_answer_not_an_error(client) -> None:
    """A first-time patient at a walk-in OPD is the common case. A screen that errors on
    them is a screen that breaks on day one."""
    kamala = await _login(client, "kamala.devi@abdm")
    session_ref = await _start_session(client, kamala)
    clinician = (
        await client.post("/mock-idp/token", json={"role": "clinician", "sub": "dr.mehta@aiia"})
    ).json()["access_token"]

    response = await client.get(
        f"/api/v1/sessions/{session_ref}/patient-context", headers=_auth(clinician)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["known"] is False
    assert body["timeline"] == []
    assert body["similar"] == []


async def test_an_uploaded_original_is_retrievable_and_is_the_bytes_that_were_sent(
    client,
) -> None:
    """The evidence drawer draws a box on this. The bytes were never being stored, so the
    box was drawn over nothing for every document a patient actually uploaded."""
    kamala = await _login(client, "kamala.devi@abdm")
    session_ref = await _start_session(client, kamala)

    source = PROJECT_ROOT / "data" / "fixtures" / "documents" / "prescription.pdf"
    sent = source.read_bytes()
    upload = await client.post(
        f"/api/v1/sessions/{session_ref}/documents",
        headers=_auth(kamala),
        files={"file": (source.name, sent, "application/pdf")},
        data={"backend": "textlayer"},
    )
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["documentId"]

    clinician = (
        await client.post("/mock-idp/token", json={"role": "clinician", "sub": "dr.mehta@aiia"})
    ).json()["access_token"]
    original = await client.get(
        f"/api/v1/sessions/{session_ref}/documents/{document_id}/file",
        headers=_auth(clinician),
    )
    assert original.status_code == 200
    assert original.content == sent
    assert original.headers["cache-control"] == "no-store"
