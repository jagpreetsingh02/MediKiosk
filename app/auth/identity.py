"""Caller identity.

Bearer tokens are ABHA-linked JWTs. When `AUTH_REQUIRED=false` (local dev and the demo) an
unauthenticated caller is resolved to the `anonymous` role, which the policy file restricts to
read-only terminology actions.

The token issuer used in development is a **mock** (`app/auth/mock_idp.py`). It is labelled as
a mock in the README, in `/about`, and in the token itself. It is never presented as a real
ABDM integration.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt

from app.core.config import settings
from app.core.errors import AuthError

ANONYMOUS_ROLE = "anonymous"


@dataclass(frozen=True, slots=True)
class Identity:
    actor: str
    role: str
    abha_ref: str | None = None
    issuer: str | None = None
    is_mock: bool = False
    #: Present only on patient tokens from the mock ABHA IdP. Used to pre-fill the kiosk so
    #: an elderly patient never types their own age; never treated as clinical content.
    demographics: dict | None = None

    @property
    def authenticated(self) -> bool:
        return self.role != ANONYMOUS_ROLE


ANONYMOUS = Identity(actor="anonymous", role=ANONYMOUS_ROLE)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Bearer token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError(f"Bearer token is not valid: {exc}") from exc


def identity_from_header(authorization: str | None) -> Identity:
    if not authorization:
        if settings.auth_required:
            raise AuthError("Authorization header is required.")
        return ANONYMOUS

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError("Authorization header must be `Bearer <token>`.")

    claims = decode_token(token)
    role = claims.get("role")
    if not role:
        raise AuthError("Token carries no `role` claim.")
    return Identity(
        actor=str(claims.get("sub") or claims.get("client_id") or "unknown"),
        role=str(role),
        abha_ref=claims.get("abha_ref"),
        issuer=claims.get("iss"),
        is_mock=str(claims.get("iss", "")).startswith("mock"),
        demographics=claims.get("demographics"),
    )
