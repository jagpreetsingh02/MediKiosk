"""Granular, revocable, audio-explained consent — Invariant 6, first half.

Consent is a **gate**, not a checkbox: `FactLedger.consent_scopes` is populated from the grant,
and `record_fact()` refuses any fact whose `required_scope` is not in it. Refusing the voice
scope does not disable a warning; it makes the microphone path structurally unable to write.

Three properties enforced here:

* **Granular.** Five independent scopes. Refusing `documents` does not affect `history`.
* **Revocable.** `revoke()` narrows the ledger's scopes immediately. Facts already recorded
  under a since-revoked scope are purged, because consent withdrawn is consent withdrawn.
* **Audio-explained.** Every scope carries `audio_en`/`audio_hi` written for someone who has
  never used a computer. `grant()` records *whether the audio was actually played*, and the
  physician screen shows a consent that was granted without it having been played.
"""
from __future__ import annotations

import functools
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from app.contracts.record import FactLedger
from app.core.config import settings
from app.core.errors import ConsentRequired, ValidationError
from app.core.logging import get_logger

log = get_logger(__name__)


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    required: bool
    title_en: str
    title_hi: str
    audio_en: str
    audio_hi: str

    def title(self, language: str) -> str:
        return getattr(self, f"title_{language}", None) or self.title_en

    def audio(self, language: str) -> str:
        return getattr(self, f"audio_{language}", None) or self.audio_en


class ConsentPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    policy_version: str
    scopes: list[Scope]
    preamble: dict[str, str]

    def by_id(self, scope_id: str) -> Scope | None:
        return next((s for s in self.scopes if s.id == scope_id), None)

    @property
    def required_ids(self) -> set[str]:
        return {s.id for s in self.scopes if s.required}


@functools.lru_cache(maxsize=1)
def load_policy() -> ConsentPolicy:
    path = settings.path("config/consent-scopes.yaml")
    return ConsentPolicy.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def presentation(language: str = "en") -> dict[str, Any]:
    """What the kiosk renders and reads aloud, before a single question is asked."""
    policy = load_policy()
    return {
        "policyVersion": policy.policy_version,
        "preamble": policy.preamble.get(language, policy.preamble["en"]),
        "scopes": [
            {
                "id": scope.id,
                "required": scope.required,
                "title": scope.title(language),
                "audio": scope.audio(language),
            }
            for scope in policy.scopes
        ],
    }


@dataclass(slots=True)
class Consent:
    consent_ref: str
    session_ref: str
    granted: set[str] = field(default_factory=set)
    refused: set[str] = field(default_factory=set)
    language: str = "en"
    audio_explained: bool = False
    policy_version: str = "1.0.0"
    granted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    revoked_at: datetime | None = None

    @property
    def active(self) -> bool:
        if self.revoked_at is not None:
            return False
        return self.expires_at is None or datetime.now(UTC) < self.expires_at

    def allows(self, scope: str) -> bool:
        return self.active and scope in self.granted

    def to_dict(self) -> dict[str, Any]:
        return {
            "consentRef": self.consent_ref,
            "sessionRef": self.session_ref,
            "granted": sorted(self.granted),
            "refused": sorted(self.refused),
            "language": self.language,
            "audioExplained": self.audio_explained,
            "policyVersion": self.policy_version,
            "grantedAt": self.granted_at.isoformat(),
            "expiresAt": self.expires_at.isoformat() if self.expires_at else None,
            "revokedAt": self.revoked_at.isoformat() if self.revoked_at else None,
            "active": self.active,
            "warning": (
                None if self.audio_explained
                else "Consent was recorded without the audio explanation being played."
            ),
        }


def grant(
    *,
    session_ref: str,
    granted: list[str],
    language: str = "en",
    audio_explained: bool = False,
    ttl_seconds: int | None = None,
) -> Consent:
    """Record a consent decision. Refuses to proceed without every required scope."""
    policy = load_policy()
    known = {s.id for s in policy.scopes}
    unknown = set(granted) - known
    if unknown:
        raise ValidationError(f"Unknown consent scope(s): {sorted(unknown)}.")

    granted_set = set(granted)
    missing = policy.required_ids - granted_set
    if missing:
        raise ConsentRequired(
            f"Cannot begin without: {sorted(missing)}. The patient may decline, in which "
            "case the session ends and nothing at all is captured — which is the correct "
            "outcome of a refusal, not an error to work around."
        )

    consent = Consent(
        consent_ref=f"consent_{uuid.uuid4().hex[:12]}",
        session_ref=session_ref,
        granted=granted_set,
        refused=known - granted_set,
        language=language,
        audio_explained=audio_explained,
        policy_version=policy.policy_version,
        expires_at=datetime.now(UTC)
        + timedelta(seconds=ttl_seconds or settings.session_ttl_seconds),
    )
    log.info(
        "consent.granted",
        session=session_ref, consent=consent.consent_ref,
        granted=sorted(granted_set), audio=audio_explained,
    )
    return consent


def apply_to_ledger(consent: Consent, ledger: FactLedger) -> None:
    """Wire consent into the choke point. After this, record_fact enforces it."""
    if not consent.active:
        raise ConsentRequired("This consent is revoked or expired; nothing may be captured.")
    ledger.consent_scopes = set(consent.granted)


def revoke(
    consent: Consent, ledger: FactLedger, *, scopes: list[str] | None = None
) -> dict[str, Any]:
    """Withdraw consent, wholly or per-scope, and purge what it covered.

    Narrowing the ledger's scopes is not enough on its own: facts already recorded under a
    scope the patient has just withdrawn must go. Consent withdrawn is consent withdrawn,
    and a record that survives it is a record the patient did not agree to.
    """
    policy = load_policy()
    targets = set(scopes) if scopes else set(consent.granted)
    unknown = targets - {s.id for s in policy.scopes}
    if unknown:
        raise ValidationError(f"Unknown consent scope(s): {sorted(unknown)}.")

    consent.granted -= targets
    consent.refused |= targets
    if not consent.granted & policy.required_ids:
        consent.revoked_at = datetime.now(UTC)

    ledger.consent_scopes = set(consent.granted)

    purged = _purge_scope_facts(ledger, targets)
    log.info(
        "consent.revoked",
        session=consent.session_ref, scopes=sorted(targets), purged=purged,
        fully_revoked=consent.revoked_at is not None,
    )
    return {
        "revokedScopes": sorted(targets),
        "remainingScopes": sorted(consent.granted),
        "factsPurged": purged,
        "sessionEnded": consent.revoked_at is not None,
    }


#: Which recorded facts each optional scope owns. Revoking a scope purges exactly these.
_SCOPE_FACT_PREDICATES = {
    "documents": lambda fact: fact.tier.value == "document",
    "voice": lambda fact: getattr(fact.source, "modality", None)
    and fact.source.modality.value == "speech",
    "ayush": lambda fact: fact.path.startswith("ayush."),
}


def _purge_scope_facts(ledger: FactLedger, scopes: set[str]) -> int:
    """Delete facts owned by a withdrawn scope, and rebuild the duplicate-detection index.

    The index has to be rebuilt from what survives, or a purged fact's digest would linger
    and silently swallow the same answer if the patient re-granted the scope and said it again.
    """
    from app.contracts.provenance import span_digest

    predicates = [_SCOPE_FACT_PREDICATES[s] for s in scopes if s in _SCOPE_FACT_PREDICATES]
    if not predicates:
        return 0
    survivors = [f for f in ledger._facts if not any(p(f) for p in predicates)]
    purged = len(ledger._facts) - len(survivors)
    ledger._facts = survivors
    ledger._digests = {f"{f.path}|{span_digest(f.source)}" for f in survivors}
    return purged


def require(consent: Consent | None, scope: str) -> None:
    """Guard for a capture endpoint. Raises rather than degrading quietly."""
    if consent is None or not consent.allows(scope):
        raise ConsentRequired(
            f"Consent scope {scope!r} has not been granted for this session."
        )
