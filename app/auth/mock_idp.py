"""⚠️ MOCK ABDM/ABHA identity provider — development and demo only.

**Ported from SIH 25026 `app/auth/mock_idp.py`**, extended with the patient-facing ABHA
login the kiosk needs: an ABHA address, a mock OTP, and a token that carries `abha_ref`.

This is **not** an ABDM integration. It issues locally-signed JWTs so the authorisation, consent
and audit paths can be exercised without ABDM sandbox credentials. Every token it mints carries
`iss=mock-abdm-idp` and `mock: true`, both surfaced in `/about`, in the kiosk UI, and in every
audit row. The kiosk shows a permanent "DEMO IDENTITY" band while such a token is in play, so
nobody watching a demo can mistake it for a live ABDM connection.

If real ABDM sandbox credentials arrive, point `JWT_ISSUER`/JWKS at the real issuer and delete
this router. Nothing else in the codebase changes.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Body

from app.auth.policy import load_policy
from app.core.config import settings
from app.core.errors import AuthError, ValidationError

router = APIRouter(prefix="/mock-idp", tags=["mock-idp"])

TOKEN_TTL = timedelta(hours=8)
#: The only OTP this mock accepts. Constant on purpose: a random OTP printed to a server log
#: is a demo failure mode waiting to happen.
DEMO_OTP = "123456"

#: Synthetic patients. No real ABHA address, no real person. Ages and genders only, because
#: the kiosk uses them to skip questions (an obstetric ROS branch, for instance).
DEMO_PATIENTS: dict[str, dict[str, Any]] = {
    "kamala.devi@abdm": {
        "display_name": "Kamala Devi",
        "age_years": 64,
        "gender": "female",
        "language": "hi",
    },
    "ramesh.kumar@abdm": {
        "display_name": "Ramesh Kumar",
        "age_years": 47,
        "gender": "male",
        "language": "hi",
    },
    "anitha.r@abdm": {
        "display_name": "Anitha R",
        "age_years": 31,
        "gender": "female",
        "language": "ta",
    },
    "demo@abdm": {
        "display_name": "Demo Patient",
        "age_years": 52,
        "gender": "male",
        "language": "en",
    },
}


def _abha_ref(abha_address: str) -> str:
    """A stable pseudonymous reference. The address itself never reaches the audit log."""
    return "abha:" + hashlib.sha256(abha_address.encode("utf-8")).hexdigest()[:24]


def _mint(claims: dict[str, Any]) -> str:
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _base_claims(sub: str, role: str, abha_ref: str | None) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": sub,
        "role": role,
        "abha_ref": abha_ref,
        "iat": int(now.timestamp()),
        "exp": int((now + TOKEN_TTL).timestamp()),
        "mock": True,
    }


@router.get("/.well-known/notice")
async def notice() -> dict[str, Any]:
    return {
        "warning": "MOCK ISSUER — not ABDM. Tokens are signed with a local development secret.",
        "issuer": settings.jwt_issuer,
        "audience": settings.jwt_audience,
        "roles": sorted(load_policy()["roles"]),
        "demoAbhaAddresses": sorted(DEMO_PATIENTS),
        "demoOtp": DEMO_OTP,
        "usage": "POST /mock-idp/abha/request-otp then /mock-idp/abha/verify-otp",
    }


@router.post("/abha/request-otp")
async def request_otp(payload: Annotated[dict, Body()]) -> dict[str, Any]:
    """Step 1 of the kiosk login. Always 'sends' an OTP; the OTP is always ``123456``."""
    address = str(payload.get("abha_address", "")).strip().lower()
    if not address:
        raise ValidationError("abha_address is required, e.g. 'demo@abdm'.")
    known = address in DEMO_PATIENTS
    return {
        "txnId": hashlib.sha256(f"{address}|{datetime.now(UTC).date()}".encode()).hexdigest()[:16],
        "abhaAddress": address,
        "otpSentTo": "+91-XXXXXX-" + hashlib.sha256(address.encode()).hexdigest()[:4],
        "known": known,
        "issuerKind": "mock",
        "demoOtp": DEMO_OTP,
        "warning": "MOCK OTP. No message was sent to anybody.",
    }


@router.post("/abha/verify-otp")
async def verify_otp(payload: Annotated[dict, Body()]) -> dict[str, Any]:
    """Step 2. Returns a patient-role token carrying `abha_ref` and the demographics."""
    address = str(payload.get("abha_address", "")).strip().lower()
    otp = str(payload.get("otp", "")).strip()
    if otp != DEMO_OTP:
        raise AuthError(f"Incorrect OTP. This mock issuer only accepts {DEMO_OTP}.")
    profile = DEMO_PATIENTS.get(address)
    if profile is None:
        # An unknown address still authenticates — the kiosk must work for a walk-in whose
        # ABHA we have no fixture for — but with no demographics to pre-fill.
        profile = {"display_name": None, "age_years": None, "gender": None, "language": "en"}
    ref = _abha_ref(address)
    claims = _base_claims(sub=address, role="patient", abha_ref=ref)
    claims["demographics"] = profile
    return {
        "access_token": _mint(claims),
        "token_type": "Bearer",
        "expires_in": int(TOKEN_TTL.total_seconds()),
        "abhaRef": ref,
        "demographics": profile,
        "issuer_kind": "mock",
        "warning": "Development token from a MOCK issuer. Not an ABDM credential.",
    }


@router.post("/token")
async def issue_token(payload: Annotated[dict, Body()]) -> dict[str, Any]:
    """Staff login. Unchanged from 25026 apart from the role set coming from policy.yaml."""
    role = payload.get("role")
    roles = load_policy()["roles"]
    if role not in roles:
        raise ValidationError(f"role must be one of {sorted(roles)}")
    claims = _base_claims(
        sub=str(payload.get("sub") or f"{role}@example.org"),
        role=str(role),
        abha_ref=payload.get("abha_ref"),
    )
    return {
        "access_token": _mint(claims),
        "token_type": "Bearer",
        "expires_in": int(TOKEN_TTL.total_seconds()),
        "issuer_kind": "mock",
        "warning": "Development token from a MOCK issuer. Not an ABDM credential.",
    }
