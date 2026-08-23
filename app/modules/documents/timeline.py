"""Chronological assembly — Module B's third stage.

Two decisions worth stating:

**Undated events are not dropped.** A patient's oldest and most important record is often the
one with no legible date. Undated events sort to the end in a clearly-labelled "date unknown"
group rather than vanishing from a timeline that then looks complete.

**Precision is carried, not flattened.** "2019" and "14 March 2019" both become a `date`, but
one is `year`-precision and one is `exact`. The physician screen renders them differently,
because "started metformin in 2019" and "started metformin on 14 March 2019" support very
different conclusions and the difference must not be invented by a sort key.
"""

from __future__ import annotations

import uuid
from datetime import date

from app.contracts.history import TimelineEvent, api_dump
from app.modules.documents.entities import ExtractedEntity

#: Order within the same date. A diagnosis contextualises the drugs and results beneath it.
_KIND_ORDER = {"diagnosis": 0, "procedure": 1, "medication": 2, "investigation": 3, "note": 4}

_PRECISION_ORDER = {"exact": 0, "month": 1, "year": 2, "relative": 3, "unknown": 4}


def _label_for(entity: ExtractedEntity) -> tuple[str, str | None]:
    detail = entity.detail
    if entity.kind == "medication":
        parts = [entity.text]
        if detail.get("dose"):
            parts.append(str(detail["dose"]))
        if detail.get("frequency"):
            parts.append(str(detail["frequency"]))
        duration = f" for {detail['duration']}" if detail.get("duration") else ""
        return " ".join(parts), (f"Prescribed{duration}".strip() or None)
    if entity.kind == "investigation":
        value = detail.get("value")
        unit = detail.get("unit") or ""
        label = f"{detail.get('display') or entity.text} {value} {unit}".strip()
        flag = detail.get("rangeFlag")
        if flag in ("low", "high"):
            low, high = detail.get("referenceLow"), detail.get("referenceHigh")
            interval = f" (reference {low}–{high})" if low is not None and high is not None else ""
            return label, f"Outside the reference interval: {flag}{interval}"
        if flag == "in_range":
            return label, "Within the reference interval"
        return label, "No reference interval available"
    return entity.text, None


def build_timeline(
    entities: list[ExtractedEntity],
    *,
    document_id: str,
    fact_ids: dict[int, str] | None = None,
    low_confidence: bool = False,
) -> list[TimelineEvent]:
    """Turn extracted entities into ordered timeline events."""
    fact_ids = fact_ids or {}
    events: list[TimelineEvent] = []

    for index, entity in enumerate(entities):
        label, detail = _label_for(entity)
        fact_id = fact_ids.get(index)
        events.append(
            TimelineEvent(
                event_id=f"evt_{uuid.uuid4().hex[:10]}",
                occurred_on=entity.observed_on,
                date_precision=entity.date_precision,  # type: ignore[arg-type]
                kind=entity.kind,  # type: ignore[arg-type]
                label=label,
                detail=detail,
                document_id=document_id,
                fact_ids=[fact_id] if fact_id else [],
                low_confidence=low_confidence or entity.handwritten,
            )
        )
    return events


def order_timeline(events: list[TimelineEvent]) -> list[TimelineEvent]:
    """Newest first, undated last. Stable, so equal keys keep document order."""
    dated = [e for e in events if e.occurred_on is not None]
    undated = [e for e in events if e.occurred_on is None]

    dated.sort(
        key=lambda e: (
            -(e.occurred_on or date.min).toordinal(),
            _PRECISION_ORDER.get(e.date_precision, 9),
            _KIND_ORDER.get(e.kind, 9),
        )
    )
    undated.sort(key=lambda e: _KIND_ORDER.get(e.kind, 9))
    return dated + undated


def group_by_period(events: list[TimelineEvent]) -> list[dict]:
    """Group for rendering: one bucket per year, plus a final 'date unknown' bucket."""
    buckets: dict[str, list[TimelineEvent]] = {}
    for event in order_timeline(events):
        key = str(event.occurred_on.year) if event.occurred_on else "unknown"
        buckets.setdefault(key, []).append(event)

    known = sorted((k for k in buckets if k != "unknown"), reverse=True)
    out = [
        {
            "period": key,
            "label": key,
            "events": [api_dump(e) for e in buckets[key]],
        }
        for key in known
    ]
    if "unknown" in buckets:
        out.append(
            {
                "period": "unknown",
                "label": "Date not legible on the document",
                "events": [api_dump(e) for e in buckets["unknown"]],
            }
        )
    return out
