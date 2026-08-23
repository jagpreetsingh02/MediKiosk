"""ABAC policy evaluation. Rules live in `config/policy.yaml`; this module only evaluates them.

Purpose-of-use is not decoration: `CLAIM` refuses candidate-tier results outright, `RESEARCH`
and `STATISTICS` strip identifiers, `STATISTICS` is aggregate-only.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from app.core.config import settings
from app.core.errors import PolicyDenied, ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Purpose(StrEnum):
    TREATMENT = "TREATMENT"
    CLAIM = "CLAIM"
    RESEARCH = "RESEARCH"
    STATISTICS = "STATISTICS"


@functools.lru_cache(maxsize=1)
def load_policy() -> dict[str, Any]:
    path = Path(settings.policy_file)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    purpose: Purpose
    role: str
    candidates_allowed: bool
    curated_allowed: bool
    strip_identifiers: bool
    aggregate_only: bool
    reason: str | None = None

    def require(self) -> Decision:
        if not self.allowed:
            raise PolicyDenied(self.reason or "Denied by policy.")
        return self


def parse_purpose(value: str | None) -> Purpose:
    if not value:
        raise ValidationError(
            "purpose-of-use is required on every request. Supply `purpose` as a query "
            "parameter or `X-Purpose-Of-Use` as a header, one of: "
            f"{', '.join(p.value for p in Purpose)}."
        )
    try:
        return Purpose(value.strip().upper())
    except ValueError as exc:
        raise ValidationError(
            f"{value!r} is not a valid purpose-of-use. Expected one of: "
            f"{', '.join(p.value for p in Purpose)}."
        ) from exc


def evaluate(
    *, role: str, purpose: Purpose, action: str, allow_curated_flag: bool = False
) -> Decision:
    policy = load_policy()
    role_rules = policy["roles"].get(role)
    purpose_rules = policy["purposes"].get(purpose.value)

    if purpose_rules is None:
        raise ValidationError(f"Purpose {purpose.value!r} is not defined in the policy file.")

    if role_rules is None:
        return Decision(
            allowed=False,
            purpose=purpose,
            role=role,
            candidates_allowed=False,
            curated_allowed=False,
            strip_identifiers=True,
            aggregate_only=False,
            reason=f"Role {role!r} is not defined in the policy.",
        )

    if purpose.value not in role_rules.get("purposes", []):
        return Decision(
            allowed=False,
            purpose=purpose,
            role=role,
            candidates_allowed=False,
            curated_allowed=False,
            strip_identifiers=True,
            aggregate_only=False,
            reason=f"Role {role!r} may not act with purpose-of-use {purpose.value}.",
        )

    if action not in role_rules.get("actions", []):
        return Decision(
            allowed=False,
            purpose=purpose,
            role=role,
            candidates_allowed=False,
            curated_allowed=False,
            strip_identifiers=True,
            aggregate_only=False,
            reason=f"Role {role!r} may not perform action {action!r}.",
        )

    curated_rule = purpose_rules.get("curated_mappings", "allow")
    curated_allowed = curated_rule == "allow" or (
        curated_rule == "require_flag" and allow_curated_flag
    )

    return Decision(
        allowed=True,
        purpose=purpose,
        role=role,
        candidates_allowed=purpose_rules.get("candidates", "allow") == "allow",
        curated_allowed=curated_allowed,
        strip_identifiers=bool(purpose_rules.get("strip_identifiers", False)),
        aggregate_only=bool(purpose_rules.get("aggregate_only", False)),
    )
