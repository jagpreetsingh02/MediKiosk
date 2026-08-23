"""The whole journey through the HTTP surface: login → consent → interview → documents →
physician review → commit → purge. If this passes, the demo works."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "documents"


@pytest.fixture
async def client(tmp_path, monkeypatch):
    """A fresh app on a throwaway SQLite file, with the in-memory session store."""
    db_path = tmp_path / "t.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("LLM_BACKEND", "offline")
    monkeypatch.setenv("SESSION_STORE_ALLOW_MEMORY_FALLBACK", "true")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")  # unreachable on purpose

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
        "app.redflags.engine",
        "app.llm.registry",
        "app.speech.registry",
        "app.modules.consent.consent",
        "app.main",
    ):
        import importlib

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


async def _patient_token(client) -> tuple[str, dict]:
    await client.post("/mock-idp/abha/request-otp", json={"abha_address": "kamala.devi@abdm"})
    response = await client.post(
        "/mock-idp/abha/verify-otp",
        json={"abha_address": "kamala.devi@abdm", "otp": "123456"},
    )
    body = response.json()
    return body["access_token"], body["demographics"]


async def _clinician_token(client) -> str:
    response = await client.post(
        "/mock-idp/token", json={"role": "clinician", "sub": "dr.mehta@aiia"}
    )
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------ system


async def test_about_declares_every_invariant_and_every_mock(client) -> None:
    body = (await client.get("/about")).json()
    assert len(body["invariants"]) == 6
    assert "MOCK" in body["mocked"]["abhaIdentity"]
    assert body["mocked"]["patientData"].startswith("100% synthetic")
    assert body["fhirVersion"] == "4.0.1"


async def test_health(client) -> None:
    assert (await client.get("/health")).json()["status"] == "ok"


# ------------------------------------------------------------------ consent gate


async def test_session_cannot_start_without_the_required_scope(client) -> None:
    token, _ = await _patient_token(client)
    response = await client.post(
        "/api/v1/sessions",
        json={"language": "en", "consentScopes": ["voice"]},
        headers=_auth(token),
    )
    assert response.status_code == 403
    assert "Cannot begin without" in response.text


async def test_consent_presentation_is_audio_explained(client) -> None:
    body = (await client.get("/api/v1/consent/presentation?language=hi")).json()
    assert body["preamble"]
    assert all(scope["audio"] for scope in body["scopes"])
    assert any(scope["required"] for scope in body["scopes"])


# ------------------------------------------------------------------ the journey


async def test_full_patient_journey(client) -> None:
    token, demographics = await _patient_token(client)
    assert demographics["age_years"] == 64

    created = await client.post(
        "/api/v1/sessions",
        json={
            "language": "en",
            "consentScopes": ["history", "voice", "documents", "abdm_share"],
            "audioExplained": True,
        },
        headers=_auth(token),
    )
    assert created.status_code == 201
    session_ref = created.json()["sessionRef"]
    assert created.json()["consent"]["audioExplained"] is True

    # --- walk the interview, answering the cardiac path -------------------
    answers = {
        "cc.text": "pain",
        "cc.duration": "days_1_3",
        "hpi.site": "chest",
        "hpi.onset": "sudden",
        "hpi.character": "pressure",
        "hpi.radiation": "jaw_neck",
        "hpi.associated": ["sweating", "breathlessness"],
        "hpi.timing": "constant",
        "hpi.exacerbating": ["worse_effort"],
        "hpi.severity": 9,
        "pmh.conditions": ["diabetes", "hypertension"],
        "pmh.hospitalised": False,
        "psh.any": False,
        "med.taking": True,
        "med.ayush_taking": False,
        "allergy.any": False,
        "fh.conditions": ["heart"],
        "ph.tobacco": "never",
        "ph.alcohol": "never",
        "ph.diet": "veg",
        "ph.sleep": "disturbed",
        "ph.bowel": "regular",
        "ph.occupation": "home",
        "ros.cardio": ["chest_pain_exertion"],
        "ros.resp": ["none"],
        "ros.gi": ["none"],
        "ros.neuro": ["none"],
        "ros.gu": ["none"],
        "ros.msk": ["none"],
        "ros.general": ["fatigue"],
    }

    escalation = None
    for _ in range(80):
        step = (
            await client.get(f"/api/v1/sessions/{session_ref}/dialogue/next", headers=_auth(token))
        ).json()
        if step["complete"]:
            break
        question = step["question"]
        qid = question["questionId"]
        if qid in answers:
            response = await client.post(
                f"/api/v1/sessions/{session_ref}/dialogue/answer",
                json={
                    "turnId": question["turnId"],
                    "questionId": qid,
                    "value": answers[qid],
                    "modality": "touch",
                },
                headers=_auth(token),
            )
            assert response.status_code == 200, response.text
            escalation = response.json()["escalation"]
        else:
            await client.post(
                f"/api/v1/sessions/{session_ref}/dialogue/skip",
                json={"questionId": qid},
                headers=_auth(token),
            )

    assert escalation is not None
    assert escalation["priority"] == "immediate"
    assert "RF-CARD-01" in {f["ruleId"] for f in escalation["flags"]}

    # --- upload a prior prescription --------------------------------------
    with (FIXTURES / "prescription.pdf").open("rb") as handle:
        upload = await client.post(
            f"/api/v1/sessions/{session_ref}/documents",
            files={"file": ("prescription.pdf", handle, "application/pdf")},
            data={"backend": "textlayer"},
            headers=_auth(token),
        )
    assert upload.status_code == 201, upload.text
    assert upload.json()["factsRecorded"] > 0

    timeline = (
        await client.get(f"/api/v1/sessions/{session_ref}/documents/timeline", headers=_auth(token))
    ).json()
    assert timeline["eventCount"] > 0

    # --- a patient may NOT commit ------------------------------------------
    refused = await client.post(
        f"/api/v1/sessions/{session_ref}/commit",
        json={"confirmed": True},
        headers=_auth(token),
    )
    assert refused.status_code == 403, "Invariant 4: only a clinician commits"

    # --- physician review ---------------------------------------------------
    clinician = await _clinician_token(client)
    summary = (
        await client.get(f"/api/v1/sessions/{session_ref}/summary", headers=_auth(clinician))
    ).json()
    assert summary["status"] == "draft"
    assert summary["traceability"]["ok"] is True
    assert summary["traceability"]["factLines"] > 5

    # click-to-source resolves
    sourced = [line for line in summary["lines"] if line["kind"] == "fact"]
    assert sourced
    for line in sourced:
        assert line["sources"], line["text"]
        for source in line["sources"]:
            assert source["verbatim"]

    fact_id = sourced[0]["sources"][0]["factId"]
    detail = (
        await client.get(
            f"/api/v1/sessions/{session_ref}/facts/{fact_id}", headers=_auth(clinician)
        )
    ).json()
    assert detail["source"]["verbatim"]
    assert detail["explanation"]

    # --- queue shows the patient at the top ---------------------------------
    queue = (await client.get("/api/v1/queue", headers=_auth(clinician))).json()
    assert queue["queue"][0]["priority"] == "immediate"

    # --- commit --------------------------------------------------------------
    unconfirmed = await client.post(
        f"/api/v1/sessions/{session_ref}/commit", json={}, headers=_auth(clinician)
    )
    assert unconfirmed.status_code == 403, "commit needs an explicit confirmation"

    committed = await client.post(
        f"/api/v1/sessions/{session_ref}/commit",
        json={"confirmed": True},
        headers=_auth(clinician),
    )
    assert committed.status_code == 200, committed.text
    body = committed.json()
    assert body["committed"] is True
    assert body["fhirVersion"] == "4.0.1"
    assert body["entries"] > 5
    # The HIS endpoint is a real socket, which does not exist inside an ASGI test. What must
    # hold is that the push reports its outcome HONESTLY and the bundle is not lost either
    # way — a commit that silently swallowed a failed push would be the actual bug.
    assert body["hisPush"]["status"] in ("accepted", "unreachable")
    if body["hisPush"]["status"] == "unreachable":
        assert "can be retried" in body["hisPush"]["detail"]

    # --- the session is purged ------------------------------------------------
    assert body["purge"]["factsDeleted"] > 0
    gone = await client.get(f"/api/v1/sessions/{session_ref}/summary", headers=_auth(clinician))
    assert gone.status_code == 410, "session data must be unreachable after purge"

    # --- but the committed bundle survives ------------------------------------
    bundle = (
        await client.get(f"/api/v1/sessions/{session_ref}/bundle", headers=_auth(clinician))
    ).json()
    resources = {entry["resource"]["resourceType"] for entry in bundle["bundle"]["entry"]}
    assert "Composition" in resources
    assert "Provenance" in resources

    # --- and the audit chain is intact ----------------------------------------
    auditor = (await client.post("/mock-idp/token", json={"role": "auditor"})).json()[
        "access_token"
    ]
    audit = (
        await client.get("/api/v1/audit/verify?purpose=RESEARCH", headers=_auth(auditor))
    ).json()
    assert audit["intact"] is True
    assert audit["totalEvents"] > 10

    # --- and the stored bundle is accepted by the documented HIS contract --------
    delivered = await client.post("/api/v1/stub-his/Bundle", json=bundle["bundle"])
    assert delivered.status_code == 201
    assert "Composition" in delivered.json()["resourceTypes"]
    received = (await client.get("/api/v1/stub-his/received")).json()
    assert received["count"] >= 1


# ------------------------------------------------------------------ guards


async def test_voice_answer_below_threshold_degrades_to_touch(client) -> None:
    token, _ = await _patient_token(client)
    session_ref = (
        await client.post(
            "/api/v1/sessions",
            json={"language": "en", "consentScopes": ["history", "voice"]},
            headers=_auth(token),
        )
    ).json()["sessionRef"]

    step = (
        await client.get(f"/api/v1/sessions/{session_ref}/dialogue/next", headers=_auth(token))
    ).json()
    question = step["question"]
    response = await client.post(
        f"/api/v1/sessions/{session_ref}/dialogue/answer/voice",
        json={
            "turnId": question["turnId"],
            "questionId": question["questionId"],
            "transcript": "mujhe dard ho raha hai",
            "confidence": 0.22,
        },
        headers=_auth(token),
    )
    body = response.json()
    assert body["voice"]["degradedToTouch"] is True
    assert body["voice"]["factsRecorded"] == 0
    assert body["question"]["touchOnly"] is True


async def test_voice_without_consent_is_refused(client) -> None:
    token, _ = await _patient_token(client)
    session_ref = (
        await client.post(
            "/api/v1/sessions",
            json={"language": "en", "consentScopes": ["history"]},
            headers=_auth(token),
        )
    ).json()["sessionRef"]
    step = (
        await client.get(f"/api/v1/sessions/{session_ref}/dialogue/next", headers=_auth(token))
    ).json()
    response = await client.post(
        f"/api/v1/sessions/{session_ref}/dialogue/answer/voice",
        json={
            "turnId": step["question"]["turnId"],
            "questionId": step["question"]["questionId"],
            "transcript": "chest pain",
            "confidence": 0.95,
        },
        headers=_auth(token),
    )
    assert response.status_code == 403


async def test_document_upload_without_consent_is_refused(client) -> None:
    token, _ = await _patient_token(client)
    session_ref = (
        await client.post(
            "/api/v1/sessions",
            json={"language": "en", "consentScopes": ["history"]},
            headers=_auth(token),
        )
    ).json()["sessionRef"]
    with (FIXTURES / "prescription.pdf").open("rb") as handle:
        response = await client.post(
            f"/api/v1/sessions/{session_ref}/documents",
            files={"file": ("prescription.pdf", handle, "application/pdf")},
            headers=_auth(token),
        )
    assert response.status_code == 403


async def test_revoking_a_scope_purges_its_facts(client) -> None:
    token, _ = await _patient_token(client)
    session_ref = (
        await client.post(
            "/api/v1/sessions",
            json={"language": "en", "consentScopes": ["history", "documents"]},
            headers=_auth(token),
        )
    ).json()["sessionRef"]

    with (FIXTURES / "prescription.pdf").open("rb") as handle:
        await client.post(
            f"/api/v1/sessions/{session_ref}/documents",
            files={"file": ("prescription.pdf", handle, "application/pdf")},
            data={"backend": "textlayer"},
            headers=_auth(token),
        )
    before = (await client.get(f"/api/v1/sessions/{session_ref}", headers=_auth(token))).json()[
        "factsRecorded"
    ]
    assert before > 0

    revoked = await client.post(
        f"/api/v1/sessions/{session_ref}/consent/revoke",
        json={"scopes": ["documents"]},
        headers=_auth(token),
    )
    assert revoked.json()["factsPurged"] > 0
    after = (await client.get(f"/api/v1/sessions/{session_ref}", headers=_auth(token))).json()[
        "factsRecorded"
    ]
    assert after < before


async def test_triage_nurse_sees_the_queue_but_not_the_narrative(client) -> None:
    """The clinically important asymmetry: a triage desk needs to know someone is urgent,
    not why."""
    nurse = (await client.post("/mock-idp/token", json={"role": "triage_nurse"})).json()[
        "access_token"
    ]
    assert (await client.get("/api/v1/queue", headers=_auth(nurse))).status_code == 200
    blocked = await client.get("/api/v1/sessions/sess_whatever/summary", headers=_auth(nurse))
    assert blocked.status_code == 403


async def test_terminology_unmapped_is_a_200_not_an_error(client) -> None:
    response = await client.get("/api/v1/terminology/search?term=some+made+up+condition")
    assert response.status_code == 200
    assert response.json()["unmapped"] is True
    assert response.json()["coding"] is None


async def test_terminology_exact_match_returns_a_retrieved_code(client) -> None:
    response = await client.get("/api/v1/terminology/search?term=Type%202%20diabetes%20mellitus")
    body = response.json()
    assert body["unmapped"] is False
    assert body["coding"]["code"] == "5A11"
    assert body["coding"]["version"] == "2026-01"


async def test_no_endpoint_returns_an_assessment(client) -> None:
    """Invariant 1 on the wire: scan the whole OpenAPI surface for a diagnosis-shaped route."""
    spec = (await client.get("/openapi.json")).json()
    for path in spec["paths"]:
        assert "diagnos" not in path.casefold()
        assert "differential" not in path.casefold()


async def test_fhir_preview_does_not_commit_or_transmit(client) -> None:
    """A jury can inspect the bundle before confirmation. Invariant 4 is untouched: preview
    builds the document and sends it nowhere."""
    token, _ = await _patient_token(client)
    session_ref = (
        await client.post(
            "/api/v1/sessions",
            json={"language": "en", "consentScopes": ["history", "abdm_share"]},
            headers=_auth(token),
        )
    ).json()["sessionRef"]

    step = (
        await client.get(
            f"/api/v1/sessions/{session_ref}/dialogue/next", headers=_auth(token)
        )
    ).json()
    await client.post(
        f"/api/v1/sessions/{session_ref}/dialogue/answer",
        json={
            "turnId": step["question"]["turnId"],
            "questionId": step["question"]["questionId"],
            "value": "pain",
            "modality": "touch",
        },
        headers=_auth(token),
    )

    clinician = await _clinician_token(client)
    # The stub receiver accumulates across the module, so measure the delta rather than
    # asserting an absolute count.
    before = (await client.get("/api/v1/stub-his/received")).json()["count"]

    preview = await client.get(
        f"/api/v1/sessions/{session_ref}/fhir/preview", headers=_auth(clinician)
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["committed"] is False
    assert body["fhirVersion"] == "4.0.1"
    assert "Composition" in body["resourceCounts"]
    assert "not been transmitted" in body["notice"]

    # Nothing was sent and nothing was stored: the committed-bundle route still 404s.
    stored = await client.get(
        f"/api/v1/sessions/{session_ref}/bundle", headers=_auth(clinician)
    )
    assert stored.status_code == 400
    after = (await client.get("/api/v1/stub-his/received")).json()["count"]
    assert after == before, "preview must not transmit"

    # And the session is still live — preview does not purge.
    assert (
        await client.get(f"/api/v1/sessions/{session_ref}", headers=_auth(token))
    ).status_code == 200


async def test_a_patient_cannot_preview_the_bundle(client) -> None:
    token, _ = await _patient_token(client)
    session_ref = (
        await client.post(
            "/api/v1/sessions",
            json={"language": "en", "consentScopes": ["history"]},
            headers=_auth(token),
        )
    ).json()["sessionRef"]
    response = await client.get(
        f"/api/v1/sessions/{session_ref}/fhir/preview", headers=_auth(token)
    )
    assert response.status_code == 403
