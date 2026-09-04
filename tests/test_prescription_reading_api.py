"""Phase 4 — the reading survives the round trip, and both halves of it travel together.

The failure this file exists to prevent is a quiet one: the interpretation reaching the
screen without the transcription beside it. That renders as a clean, confident list of
medicines with no way for anyone — patient, pharmacist or physician — to check it against the
paper. Every assertion here is a variation on "both, or neither".
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "documents"


@pytest.fixture
async def client(tmp_path, monkeypatch):
    db_path = tmp_path / "reading.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("LLM_BACKEND", "offline")
    monkeypatch.setenv("SESSION_STORE_ALLOW_MEMORY_FALLBACK", "true")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")

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


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _session_with_documents(client) -> tuple[str, str]:
    await client.post("/mock-idp/abha/request-otp", json={"abha_address": "kamala.devi@abdm"})
    token = (
        await client.post(
            "/mock-idp/abha/verify-otp",
            json={"abha_address": "kamala.devi@abdm", "otp": "123456"},
        )
    ).json()["access_token"]
    session_ref = (
        await client.post(
            "/api/v1/sessions",
            json={"language": "en", "consentScopes": ["history", "documents"]},
            headers=_auth(token),
        )
    ).json()["sessionRef"]
    return token, session_ref


async def _upload(client, token: str, session_ref: str) -> dict:
    with (FIXTURES / "prescription.pdf").open("rb") as handle:
        response = await client.post(
            f"/api/v1/sessions/{session_ref}/documents",
            files={"file": ("prescription.pdf", handle, "application/pdf")},
            headers=_auth(token),
        )
    assert response.status_code == 201, response.text
    return response.json()


async def test_upload_returns_the_transcription_and_the_interpretation(client) -> None:
    token, session_ref = await _session_with_documents(client)
    body = await _upload(client, token, session_ref)

    assert set(body) >= {"rawOcrText", "interpretedText", "medications"}
    assert "METFORMIN" in body["rawOcrText"], "the literal transcription must survive"
    assert "Metformin 500 mg" in body["interpretedText"]
    assert len(body["medications"]) == 4


async def test_the_interpretation_never_travels_without_the_transcription(client) -> None:
    """Both keys, on every route that carries either. This is the invariant of the feature."""
    token, session_ref = await _session_with_documents(client)
    await _upload(client, token, session_ref)

    listed = (
        await client.get(f"/api/v1/sessions/{session_ref}/documents", headers=_auth(token))
    ).json()["documents"][0]
    assert listed["interpretedText"]
    assert listed["rawOcrText"]
    for medication in listed["medications"]:
        assert medication["rawText"], "an interpreted line with no transcription cannot be checked"


async def test_every_field_carries_its_own_confidence_and_provenance(client) -> None:
    token, session_ref = await _session_with_documents(client)
    body = await _upload(client, token, session_ref)

    for medication in body["medications"]:
        assert 0.0 <= medication["ocrConfidence"] <= 1.0
        assert 0.0 <= medication["interpretationConfidence"] <= 1.0
        assert isinstance(medication["needsVerification"], bool)
        assert medication["nameMatch"]["status"]
        for name, found in medication["fields"].items():
            assert found["raw"], f"{name} has no raw text"
            assert found["source"], f"{name} has no provenance"


async def test_ocr_and_interpretation_confidence_are_reported_separately(client) -> None:
    """They are independent, and one number cannot carry both.

    A crisp photograph of an unknown drug has high OCR confidence and no interpretation. A
    smudged photograph of a familiar one has the reverse. Collapsing them loses the
    distinction a reviewer needs most.
    """
    token, session_ref = await _session_with_documents(client)
    body = await _upload(client, token, session_ref)
    medication = body["medications"][0]
    assert "ocrConfidence" in medication and "interpretationConfidence" in medication


async def test_the_reading_is_stored_not_recomputed(client) -> None:
    """It is a record of what the patient was shown. Re-deriving it later against an edited
    drug dictionary would silently rewrite what happened."""
    from sqlalchemy import select

    from app.db.models import SessionDocument
    from app.db.session import get_sessionmaker

    token, session_ref = await _session_with_documents(client)
    await _upload(client, token, session_ref)

    async with get_sessionmaker()() as db:
        row = (await db.execute(select(SessionDocument))).scalars().first()
        assert row is not None
        assert row.reading_json is not None
        assert row.reading_json["rawOcrText"]
        assert row.reading_json["medications"]


async def test_a_lab_report_yields_no_medications_rather_than_phantom_ones(client) -> None:
    """Seven lines of a blood report each carry a word and a number. None of them is a drug."""
    token, session_ref = await _session_with_documents(client)
    with (FIXTURES / "lab_report.pdf").open("rb") as handle:
        body = (
            await client.post(
                f"/api/v1/sessions/{session_ref}/documents",
                files={"file": ("lab_report.pdf", handle, "application/pdf")},
                headers=_auth(token),
            )
        ).json()
    assert body["medications"] == []
    assert body["interpretedText"] == ""
    assert body["rawOcrText"], "the transcription is still returned — there was text on it"
