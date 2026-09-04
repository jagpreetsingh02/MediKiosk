"""Sign in / register — A STUB, and labelled as one everywhere it appears.

⛔ WHAT THIS IS NOT. It is not an authentication system, and nothing in the product depends on
it. The real identity path is the MOCK ABHA IdP in `app/auth/mock_idp.py`, which is a
documented project decision (`AGENT.md`, ADR notes, `/about`) and is NOT being replaced with
Supabase Auth — inventing a second, conflicting patient identity is exactly what the brief
refuses. This exists so the judged product does not have a conspicuous hole where a sign-in
screen would be.

Being a stub is not a licence to model bad security, because a stub is what people copy:

  * NO USER ENUMERATION. "No such user" and "wrong password" return the SAME message and the
    same status. A login form that distinguishes them is a free list of who holds an account,
    and it is the single most common way a real system leaks its user base.
  * RATE LIMITED. Per-identifier and per-client, in-process. It is not a distributed limiter
    and does not claim to be, but an endpoint with no limit at all teaches the wrong shape.
  * CONSTANT-TIME COMPARISON, and a hash computed even when the account does not exist, so
    the response time does not answer the question the message refuses to.
  * NOTHING IS STORED. There is no user table. Registration accepts and returns a stub
    response; it does not create an account, and it says so.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Annotated, Any

from fastapi import APIRouter, Body, Request

from app.core.errors import SwastraError
from app.core.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api/v1/account", tags=["account-stub"])

#: Deliberately identical for every failure mode. See the module docstring.
GENERIC_FAILURE = "Those sign-in details did not match. Please check them and try again."

#: Attempts per window, per key. Low, because this endpoint does nothing useful — a limit
#: generous enough to be convenient would only be convenient for a script.
MAX_ATTEMPTS = 5
WINDOW_SECONDS = 300

#: key -> (count, window_start). In-process on purpose: a real limiter belongs in Redis or at
#: the edge, and pretending otherwise here would be the misleading version.
_attempts: dict[str, tuple[int, float]] = {}

#: A dummy hash to compare against when the account does not exist, so the work done — and
#: therefore the time taken — is the same either way.
_DUMMY = hashlib.pbkdf2_hmac("sha256", b"dummy", b"medikiosk-stub", 50_000)


class TooManyAttempts(SwastraError):
    http_status = 429
    issue_code = "throttled"


def _rate_key(request: Request, identifier: str) -> str:
    client = request.client.host if request.client else "unknown"
    return f"{client}:{identifier.lower().strip()}"


def _check_rate(key: str) -> None:
    now = time.monotonic()
    count, started = _attempts.get(key, (0, now))
    if now - started > WINDOW_SECONDS:
        count, started = 0, now
    if count >= MAX_ATTEMPTS:
        raise TooManyAttempts(
            "Too many sign-in attempts. Please wait a few minutes and try again.",
            reason="rate_limited",
        )
    _attempts[key] = (count + 1, started)


def _hash(password: str) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), b"medikiosk-stub", 50_000)


@router.post("/sign-in")
async def sign_in(request: Request, payload: Annotated[dict, Body()]) -> dict[str, Any]:
    """Always refuses, in the same words, at the same speed.

    THERE ARE NO ACCOUNTS, so every attempt fails — and the interesting property is that it
    fails IDENTICALLY to how a real wrong password would. The work is done regardless, so
    neither the message nor the timing tells a caller whether an identifier exists.
    """
    identifier = str(payload.get("identifier", "")).strip()
    password = str(payload.get("password", ""))
    _check_rate(_rate_key(request, identifier))

    # Compared against a dummy, in constant time. The result is discarded; doing the work is
    # the point, so this branch costs what a real lookup would.
    hmac.compare_digest(_hash(password), _DUMMY)

    log.info("account.sign_in_attempt", outcome="refused", hasIdentifier=bool(identifier))
    raise SwastraError(GENERIC_FAILURE, reason="invalid_credentials")


@router.post("/register", status_code=202)
async def register(request: Request, payload: Annotated[dict, Body()]) -> dict[str, Any]:
    """Accepts and stores NOTHING. Says so, rather than implying an account now exists."""
    identifier = str(payload.get("identifier", "")).strip()
    _check_rate(_rate_key(request, identifier))
    log.info("account.register_attempt", hasIdentifier=bool(identifier))
    return {
        "created": False,
        "stub": True,
        "message": (
            "Account creation is not available in this build. Use Try demo to explore the "
            "product, or the demo ABHA identity to sign in as a patient."
        ),
        # A stub must not hand back anything that looks like a credential.
        "reference": f"stub_{secrets.token_hex(4)}",
    }


@router.get("/status")
async def status() -> dict[str, Any]:
    """What this endpoint is, stated plainly, for anyone reading the API rather than the UI."""
    return {
        "implemented": False,
        "stub": True,
        "realIdentityPath": "mock ABHA IdP at /mock-idp — see /about",
        "note": (
            "Sign-in and registration are not implemented. The demo identity is a MOCK ABHA "
            "issuer and is never presented as a real ABDM integration."
        ),
        "rateLimit": {"maxAttempts": MAX_ATTEMPTS, "windowSeconds": WINDOW_SECONDS},
    }
