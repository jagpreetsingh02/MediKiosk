"""Upload → OCR → entities → facts → timeline. Module B, end to end.

Every fact written here is `document` tier and carries page + bounding box, so clicking a
line on the physician screen scrolls the scan to the exact region it came from.

The handwriting lane is enforced structurally: `ingest()` writes facts for confident entities
only. Low-confidence ones are returned separately and become facts *only* when a human calls
`verify_entity()`. There is no code path from a handwritten scrawl to the record without a
person in between.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.contracts.history import DocumentRef, TimelineEvent
from app.contracts.provenance import DocumentSpan, Fact, SourceTier
from app.contracts.record import FactLedger, record_fact
from app.core.config import settings
from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.modules.documents.backends import OCRResult, get_ocr_backend
from app.modules.documents.entities import ExtractedEntity, extract_entities, page_summary
from app.modules.documents.timeline import build_timeline, order_timeline

log = get_logger(__name__)

#: Where each entity kind lands in the history. Repeating groups, so index-addressed.
_GROUP_FOR = {
    "medication": ("medications", "name"),
    "diagnosis": ("problems", "reported_term"),
    "investigation": ("investigations", "analyte"),
    "procedure": ("procedures", "name"),
}


@dataclass(slots=True)
class IngestResult:
    document_id: str
    filename: str
    backend: str
    pages: list[dict[str, Any]]
    mean_confidence: float
    facts: list[Fact] = field(default_factory=list)
    timeline: list[TimelineEvent] = field(default_factory=list)
    #: The handwriting lane. Never merged without a human.
    needs_verification: list[dict[str, Any]] = field(default_factory=list)
    entities: list[ExtractedEntity] = field(default_factory=list)
    ocr: OCRResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "documentId": self.document_id,
            "filename": self.filename,
            "backend": self.backend,
            "pages": self.pages,
            "meanConfidence": round(self.mean_confidence, 4),
            "factsRecorded": len(self.facts),
            "timeline": [e.model_dump(mode="json") for e in self.timeline],
            "needsVerification": self.needs_verification,
            "lowConfidenceCount": len(self.needs_verification),
        }

    def document_ref(self) -> DocumentRef:
        return DocumentRef(
            document_id=self.document_id,
            filename=self.filename,
            pages=len(self.pages),
            ocr_backend=self.backend,
            mean_confidence=self.mean_confidence,
            low_confidence_pages=sorted(
                {int(e["page"]) for e in self.needs_verification}
            ),
            uploaded_at=datetime.now(UTC),
        )


def _next_index(ledger: FactLedger, group: str) -> int:
    used = {
        int(path.split("[")[1].split("]")[0])
        for path in ledger.paths()
        if path.startswith(f"{group}[")
    }
    return max(used) + 1 if used else 0


def _record_entity(
    ledger: FactLedger,
    entity: ExtractedEntity,
    document_id: str,
    known_paths: set[str],
    backend: str,
) -> list[Fact]:
    """Write one entity's facts. Every one is document-tier with page and bbox."""
    group_field = _GROUP_FOR.get(entity.kind)
    if group_field is None:
        return []
    group, primary = group_field
    index = _next_index(ledger, group)

    def span() -> DocumentSpan:
        return DocumentSpan(
            verbatim=entity.source_text,
            document_id=document_id,
            page=entity.page,
            bbox=entity.bbox,
            ocr_confidence=entity.confidence,
            ocr_backend=backend,
            handwritten=entity.handwritten,
        )

    written: list[Fact] = []

    def write(field_name: str, value: Any) -> None:
        path = f"{group}[{index}].{field_name}"
        if path not in known_paths:
            return
        try:
            written.append(
                record_fact(
                    ledger, path=path, value=value, tier=SourceTier.DOCUMENT,
                    source=span(), confidence=entity.confidence,
                    provenance_note=f"ocr:{backend}", known_paths=known_paths,
                    supersede=False,
                )
            )
        except Exception as exc:  # a single unparseable field must not lose the document
            log.warning("document.fact_rejected", path=path, error=str(exc)[:160])

    write(primary, entity.text)
    detail = entity.detail
    if entity.kind == "medication":
        if detail.get("dose"):
            write("dose", detail["dose"])
        if detail.get("frequencyRaw"):
            write("frequency", detail["frequencyRaw"])
        if detail.get("route"):
            write("route", detail["route"])
    elif entity.kind == "investigation":
        if detail.get("value") is not None:
            write("value", str(detail["value"]))
    elif entity.kind == "diagnosis" and entity.observed_on:
        write("reported_year", str(entity.observed_on.year))
    return written


def ingest(
    ledger: FactLedger,
    data: bytes,
    *,
    filename: str,
    media_type: str,
    known_paths: set[str],
    backend_name: str | None = None,
    sex: str | None = None,
    document_id: str | None = None,
) -> IngestResult:
    """Run the whole Module B pipeline for one uploaded file."""
    if len(data) > settings.max_upload_bytes:
        raise ValidationError(
            f"{filename} is {len(data) // 1024} KB; the limit is "
            f"{settings.max_upload_bytes // 1024} KB."
        )
    if not data:
        raise ValidationError(f"{filename} is empty.")

    backend = get_ocr_backend(backend_name)
    ocr = backend.read(data, filename=filename, media_type=media_type)
    doc_id = document_id or f"doc_{uuid.uuid4().hex[:10]}"

    confident, needs_check = extract_entities(ocr, sex=sex)

    facts: list[Fact] = []
    fact_index: dict[int, str] = {}
    for position, entity in enumerate(confident):
        written = _record_entity(ledger, entity, doc_id, known_paths, backend.name)
        facts.extend(written)
        if written:
            fact_index[position] = written[0].fact_id

    timeline = order_timeline(
        build_timeline(confident, document_id=doc_id, fact_ids=fact_index)
    )

    log.info(
        "document.ingested",
        document=doc_id, backend=backend.name, pages=len(ocr.pages),
        entities=len(confident), needs_verification=len(needs_check),
        facts=len(facts),
    )

    return IngestResult(
        document_id=doc_id,
        filename=filename,
        backend=backend.name,
        pages=[page_summary(p) for p in ocr.pages],
        mean_confidence=ocr.mean_confidence,
        facts=facts,
        timeline=timeline,
        needs_verification=[
            {**e.to_dict(), "entityIndex": i} for i, e in enumerate(needs_check)
        ],
        entities=confident,
        ocr=ocr,
    )


def verify_entity(
    ledger: FactLedger,
    result: IngestResult,
    *,
    entity_index: int,
    accepted: bool,
    verified_by: str,
    known_paths: set[str],
    corrected_text: str | None = None,
) -> list[Fact]:
    """A human accepted (or rejected) a low-confidence entity. The only way into the record.

    A correction is recorded against the *original* OCR span, not a fabricated one: the
    physician's screen then shows the scrawl the value came from next to the value a person
    read it as, which is exactly what a later reviewer needs to see.
    """
    pending = [e for e in result.needs_verification if e["entityIndex"] == entity_index]
    if not pending:
        raise ValidationError(f"No pending entity at index {entity_index}.")
    if not accepted:
        log.info("document.entity_rejected", document=result.document_id, index=entity_index)
        return []

    raw = pending[0]
    entity = ExtractedEntity(
        kind=raw["kind"],
        text=corrected_text or raw["text"],
        page=int(raw["page"]),
        bbox=type(result.entities[0].bbox)(**raw["bbox"]) if result.entities
        else __import__("app.contracts.provenance", fromlist=["BoundingBox"]).BoundingBox(**raw["bbox"]),
        confidence=float(raw["confidence"]),
        handwritten=bool(raw["handwritten"]),
        source_text=raw["sourceText"],
        detail=dict(raw["detail"]),
    )
    facts = _record_entity(ledger, entity, result.document_id, known_paths, result.backend)
    for fact in facts:
        log.info(
            "document.entity_verified",
            document=result.document_id, by=verified_by, fact=fact.fact_id,
            corrected=bool(corrected_text),
        )
    return facts
