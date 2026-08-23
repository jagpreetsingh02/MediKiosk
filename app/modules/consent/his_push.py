"""Pushing the committed bundle to the HIS. Invariant 4 lives at the top of this file.

`push()` refuses to run unless a physician has committed. There is no auto-submit, no
"submit on session end", and no background job that pushes drafts. The patient finishing the
interview does not send anything anywhere; a physician clicking confirm does.

The endpoint is a documented FHIR `POST /Bundle`, with a stub receiver in this repo
(`app/api/routes_stub_his.py`) so the whole path is exercisable end to end without a hospital
vendor. That is the full scope: no vendor-specific integration, per the brief.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import PolicyDenied
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class PushResult:
    ok: bool
    status: str
    detail: str
    endpoint: str
    location: str | None = None
    pushed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "detail": self.detail,
            "endpoint": self.endpoint,
            "location": self.location,
            "pushedAt": self.pushed_at.isoformat() if self.pushed_at else None,
        }


def assert_committed(*, committed_by: str | None, physician_confirmed: bool) -> None:
    """Invariant 4. Called before anything leaves the building."""
    if not physician_confirmed or not committed_by:
        raise PolicyDenied(
            "Nothing reaches the HIS or the ABHA record until a physician explicitly "
            "confirms. This summary is still a draft."
        )


async def push(
    bundle: dict[str, Any],
    *,
    committed_by: str,
    physician_confirmed: bool,
    consent_allows_share: bool,
    endpoint: str | None = None,
) -> PushResult:
    """POST the document Bundle. Two gates before the network call, both hard."""
    assert_committed(committed_by=committed_by, physician_confirmed=physician_confirmed)

    if not consent_allows_share:
        # Not an error: the patient declined ABDM sharing and the physician still sees
        # everything today. The bundle is simply not sent.
        return PushResult(
            ok=True,
            status="not_shared",
            detail=(
                "The patient did not grant the abdm_share scope. The summary was shown to "
                "the physician and was not transmitted anywhere."
            ),
            endpoint=endpoint or settings.his_fhir_endpoint,
        )

    target = endpoint or settings.his_fhir_endpoint
    try:
        async with httpx.AsyncClient(timeout=settings.his_push_timeout_seconds) as client:
            response = await client.post(
                target,
                json=bundle,
                headers={
                    "Content-Type": "application/fhir+json",
                    "X-Committed-By": committed_by,
                },
            )
        ok = response.status_code in (200, 201, 202)
        log.info("his.push", endpoint=target, status=response.status_code, ok=ok)
        return PushResult(
            ok=ok,
            status="accepted" if ok else f"rejected_{response.status_code}",
            detail=response.text[:400],
            endpoint=target,
            location=response.headers.get("Location"),
            pushed_at=datetime.now(UTC),
        )
    except httpx.HTTPError as exc:
        log.warning("his.push_failed", endpoint=target, error=str(exc)[:200])
        return PushResult(
            ok=False,
            status="unreachable",
            detail=(
                f"The HIS endpoint did not respond: {exc}. The bundle is stored locally and "
                "can be retried; nothing has been lost."
            ),
            endpoint=target,
        )
