"""Freezing a brief as it was rendered.

This is where the clock lives. `brief.assemble` is pure and carries no timestamp precisely so
that byte-equality can be asserted on it; the moment of rendering is metadata about the
render, and it is stamped here instead.

A snapshot is a record of what was SHOWN, never a cache. Nothing reads it to avoid work — the
live brief is always reassembled from current rows, because a physician opening a record today
must see today's facts. The snapshot answers a different question: what did the person who
confirmed this actually have in front of them?
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.durable import ReportSnapshot
from app.modules.report.brief import REPORT_VERSION


async def write(
    db: AsyncSession,
    *,
    encounter_id: int,
    payload: dict[str, Any],
    audience: str = "clinician",
) -> ReportSnapshot:
    """Freeze one rendered brief. The caller commits."""
    row = ReportSnapshot(
        snapshot_ref=f"rep_{uuid.uuid4().hex[:12]}",
        encounter_id=encounter_id,
        report_version=REPORT_VERSION,
        audience=audience,
        generated_at=datetime.now(UTC),
        payload_json=payload,
    )
    db.add(row)
    await db.flush()
    return row


async def latest(
    db: AsyncSession, *, encounter_id: int, audience: str = "clinician"
) -> ReportSnapshot | None:
    return (
        await db.execute(
            select(ReportSnapshot)
            .where(
                ReportSnapshot.encounter_id == encounter_id,
                ReportSnapshot.audience == audience,
            )
            .order_by(ReportSnapshot.generated_at.desc(), ReportSnapshot.id.desc())
        )
    ).scalars().first()


def describe(row: ReportSnapshot) -> dict[str, Any]:
    """A snapshot for the wire, with its version stated rather than assumed.

    `reportVersionMatchesCurrent` is the honest part: a snapshot written by an older assembler
    is still exactly what the physician saw, and saying so is better than silently re-rendering
    it with today's code and calling it the same document.
    """
    return {
        "snapshotRef": row.snapshot_ref,
        "reportVersion": row.report_version,
        "reportVersionMatchesCurrent": row.report_version == REPORT_VERSION,
        "audience": row.audience,
        "generatedAt": row.generated_at.isoformat(),
        "payload": row.payload_json,
    }
