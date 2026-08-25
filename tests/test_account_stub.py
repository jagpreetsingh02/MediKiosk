"""The account stub is a stub — but it must not model bad security.

A stub is what people copy. So the two properties that are cheap to get right and expensive
to retrofit are asserted here, even though nothing in the product depends on this endpoint:

  NO USER ENUMERATION. "No such user" and "wrong password" must be indistinguishable — same
  status, same message. A login form that tells them apart hands out a free list of who holds
  an account, and it is the most common way a real system leaks its user base.

  RATE LIMITED. An unlimited endpoint teaches the wrong shape even when it does nothing.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import routes_account
from app.main import app


@pytest.fixture(autouse=True)
def _clear_limiter():
    """Each test starts with a fresh window, or ordering decides the outcome."""
    routes_account._attempts.clear()
    yield
    routes_account._attempts.clear()


async def _post(path: str, payload: dict) -> tuple[int, dict]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(path, json=payload)
        return response.status_code, response.json()


def _diagnostics(body: dict) -> str:
    return body.get("issue", [{}])[0].get("diagnostics", "")


async def test_an_unknown_identifier_is_indistinguishable_from_a_wrong_password() -> None:
    """THE ASSERTION THAT MATTERS. Different inputs, byte-identical refusals."""
    unknown_status, unknown_body = await _post(
        "/api/v1/account/sign-in",
        {"identifier": "definitely-not-a-user@nowhere.invalid", "password": "x"},
    )
    routes_account._attempts.clear()
    known_status, known_body = await _post(
        "/api/v1/account/sign-in", {"identifier": "dr.mehta@aiia", "password": "x"}
    )

    assert unknown_status == known_status
    assert _diagnostics(unknown_body) == _diagnostics(known_body)
    assert _diagnostics(unknown_body) == routes_account.GENERIC_FAILURE


async def test_the_refusal_never_names_the_reason() -> None:
    """Wording that leaks the distinction the status code refuses to."""
    _, body = await _post("/api/v1/account/sign-in", {"identifier": "a@b.c", "password": "x"})
    message = _diagnostics(body).lower()
    for leak in ("no such", "not found", "unknown user", "incorrect password",
                 "wrong password", "does not exist", "no account"):
        assert leak not in message, f"the refusal reveals {leak!r}"


async def test_sign_in_is_rate_limited() -> None:
    """The limit must actually trip, not merely be configured."""
    payload = {"identifier": "ratetest@example.com", "password": "x"}
    codes = [(await _post("/api/v1/account/sign-in", payload))[0]
             for _ in range(routes_account.MAX_ATTEMPTS + 2)]
    assert codes[routes_account.MAX_ATTEMPTS - 1] == 400, "limit tripped too early"
    assert codes[routes_account.MAX_ATTEMPTS] == 429, "limit never tripped"
    assert codes[-1] == 429


async def test_registration_creates_nothing_and_says_so() -> None:
    """A stub must not imply an account now exists."""
    status, body = await _post(
        "/api/v1/account/register", {"identifier": "new@example.com", "password": "x"}
    )
    assert status == 202
    assert body["created"] is False
    assert body["stub"] is True
    assert "not available" in body["message"].lower()


async def test_registration_hands_back_nothing_that_looks_like_a_credential() -> None:
    _, body = await _post(
        "/api/v1/account/register", {"identifier": "new@example.com", "password": "x"}
    )
    blob = str(body).lower()
    for leak in ("token", "jwt", "bearer", "secret", "session"):
        assert leak not in blob, f"the stub returned something resembling a credential: {leak}"


async def test_the_mock_abha_path_is_named_as_the_real_one_and_as_a_mock() -> None:
    """The documented project rule: the demo identity stays, and stays labelled a mock."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        body = (await client.get("/api/v1/account/status")).json()
    assert body["implemented"] is False
    assert body["stub"] is True
    assert "mock" in body["realIdentityPath"].lower()
    assert "mock" in body["note"].lower()


def test_no_user_table_was_introduced() -> None:
    """Supabase Auth is NOT being adopted, and nor is a parallel user table.

    A second patient identity is exactly what the brief refuses. This fails the build if a
    later change quietly adds one.
    """
    from app.db.base import Base

    tables = set(Base.metadata.tables)
    for forbidden in ("user", "users", "account", "accounts", "auth_user", "credential"):
        assert forbidden not in tables, (
            f"a {forbidden!r} table appeared — the identity path is the mock ABHA IdP, and a "
            "second identity store is what the brief explicitly refuses"
        )
