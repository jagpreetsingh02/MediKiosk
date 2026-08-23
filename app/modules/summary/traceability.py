"""⛔ The traceability gate — Invariant 4, and the last defence for Invariant 2.

After the summary is assembled (and after any prose smoothing), **every clinical claim in it
must resolve to a `record_fact()` entry, or generation fails**. Not a warning: a
`TraceabilityError`, and no summary is returned.

Two checks, and they catch different failures:

1. **Line-level.** Every `kind="fact"` line names at least one fact id, and every id it names
   exists in the ledger. Catches a template bug that renders a value without carrying its
   provenance.

2. **Token-level.** Every clinically-meaningful token in the rendered prose appears either in
   a recorded fact's value, in its verbatim source, or in the fixed template vocabulary.
   Catches the failure that actually matters: prose smoothing introducing a word — "crushing",
   "radiating", "severe" — that no fact supports. This is why smoothing is allowed at all.

The stopword and template vocabularies are deliberately explicit rather than statistical. A
clever check that "usually" catches hallucinations is not a guarantee, and this needs to be one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache as _cache
from typing import Any

from app.contracts.record import FactLedger
from app.core.errors import TraceabilityError
from app.core.logging import get_logger
from app.modules.summary.assemble import Summary, SummaryLine

log = get_logger(__name__)

#: Words that carry no clinical claim. Everything else must be traceable.
STOPWORDS = frozenset(
    """
a an the and or but if then than that this these those of in on at to from for with without
by as is are was were be been being has have had do does did no not none nor so such it its
their there here when while during over under about into onto up down out off again further
once each few more most other some any all both which who whom whose what where why how
patient reports reported states stated says said denies denied describes described
""".split()
)

#: Vocabulary the TEMPLATE itself introduces. Fixed strings from assemble.py, never from a
#: model, so they are traceable to the code rather than to a fact.
TEMPLATE_VOCABULARY = frozenset(
    """
presenting complaint history illness escalation past medical surgical medicines allergies
prior records family personal review systems ayurvedic assessment covered patient years
medication reported unmapped undated page pages read mean confidence need verification
declined answer asked immediate urgent emergency rule fired captured applicable statement
low priority treat gaps unknown negative findings draft structured diagnosis differential
treatment offered implied edit confirm reaches record male female other site onset character
radiation associated timing exacerbating severity conditions hospitalised hospital reason
taking substance reaction tobacco alcohol diet sleep bowel occupation pregnancy general
cardiovascular respiratory gastrointestinal neurological genitourinary musculoskeletal
prakriti vikriti sara samhanana pramana satmya sattva ahara shakti vyayama vaya agni koshtha
vihara nidra build backend textlayer tesseract not this is only was of the
requires verification sources disagree vs page
""".split()
)

_TOKEN = re.compile(r"[a-zA-Zऀ-෿]{3,}")


@dataclass(slots=True)
class TraceabilityReport:
    ok: bool
    lines_checked: int = 0
    fact_lines: int = 0
    #: Lines making a clinical claim with no fact id at all.
    untraced_lines: list[str] = field(default_factory=list)
    #: Fact ids referenced by the summary that do not exist in the ledger.
    dangling_fact_ids: list[str] = field(default_factory=list)
    #: Words in the prose that no recorded fact supports. The hallucination detector.
    unsupported_tokens: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "linesChecked": self.lines_checked,
            "factLines": self.fact_lines,
            "untracedLines": self.untraced_lines,
            "danglingFactIds": self.dangling_fact_ids,
            "unsupportedTokens": self.unsupported_tokens,
        }


@_cache
def _authored_vocabulary() -> frozenset[str]:
    """Words that come from STATIC, CLINICIAN-REVIEWED content in version control.

    The ontology's labels and option text, and the red-flag rules' labels and rationales.
    These are not model output — they are data a clinician wrote and a reviewer read, and
    they are as traceable as the template itself. The check exists to catch a MODEL putting
    a word into a patient's summary; excluding authored YAML does not weaken it, and
    `test_traceability_rejects_a_model_invented_word` proves the teeth are still there.
    """
    from app.contracts.contradictions import load_rules as load_contradiction_rules
    from app.modules.dialogue.ontology import load_ontology
    from app.redflags.engine import load_rules

    words: set[str] = set()
    for question in load_ontology(ayush=True).by_id.values():
        for chunk in (
            question.physician_label(),
            *question.prompt.values(),
            *question.help.values(),
        ):
            words.update(t.casefold() for t in _TOKEN.findall(chunk))
        for option in question.options:
            # `term` is the terminology phrase the option maps to ("Type 2 diabetes
            # mellitus"). Authored in the ontology and reviewed like everything else in it.
            for chunk in (option.label_en, option.label_hi or "", option.term or ""):
                words.update(t.casefold() for t in _TOKEN.findall(chunk))
        if question.scale:
            for chunk in (*question.scale.anchors_en, *question.scale.anchors_hi):
                words.update(t.casefold() for t in _TOKEN.findall(chunk))
    for rule in load_rules().rules:
        for chunk in (rule.id, rule.label, rule.rationale):
            words.update(t.casefold() for t in _TOKEN.findall(chunk))
    for denial in load_contradiction_rules().denials:
        for chunk in (denial.id, denial.label, denial.question or ""):
            words.update(t.casefold() for t in _TOKEN.findall(chunk))
    return frozenset(words)


def _supported_vocabulary(ledger: FactLedger) -> set[str]:
    """Every word any recorded fact licenses: its value, and its verbatim source."""
    words: set[str] = set()
    for fact in ledger.facts:
        for chunk in (
            str(fact.value),
            fact.source.verbatim,
            fact.source.verbatim_translated or "",
            fact.path.replace(".", " ").replace("_", " "),
            # The document id appears in a contradiction's "origin" text. It is part of the
            # fact's own source, so it is as licensed as the verbatim is.
            str(getattr(fact.source, "document_id", "") or ""),
        ):
            words.update(t.casefold() for t in _TOKEN.findall(chunk))
    return words


def check(
    summary: Summary, ledger: FactLedger, *, retrieved_codings: set[str] | None = None
) -> TraceabilityReport:
    """Run both checks. Returns a report; does not raise. `enforce()` raises.

    `retrieved_codings` licenses display names that came out of `emit_coding()`. Those have
    a *stronger* provenance than a fact — they were read from a version-pinned CodeSystem and
    cannot have been generated (Invariant 5) — so admitting them does not weaken the check.
    They must be passed explicitly rather than inferred, so that nothing else can slip in
    under the same allowance.
    """
    known_ids = {f.fact_id for f in ledger.facts}
    supported = (
        _supported_vocabulary(ledger)
        | TEMPLATE_VOCABULARY
        | STOPWORDS
        | _authored_vocabulary()
        | {t.casefold() for text in (retrieved_codings or set()) for t in _TOKEN.findall(text)}
    )

    report = TraceabilityReport(ok=True)

    for section in summary.sections:
        for line in section.lines:
            report.lines_checked += 1
            if line.kind != "fact":
                continue
            report.fact_lines += 1

            if not line.fact_ids:
                report.untraced_lines.append(line.text)
                continue

            dangling = [fid for fid in line.fact_ids if fid not in known_ids]
            report.dangling_fact_ids.extend(dangling)

            for token in _TOKEN.findall(line.text):
                lowered = token.casefold()
                if lowered in supported:
                    continue
                # Numbers, units and punctuation-joined fragments are not clinical claims.
                if lowered.isnumeric():
                    continue
                report.unsupported_tokens.append({"token": token, "line": line.text})

    report.ok = not (report.untraced_lines or report.dangling_fact_ids or report.unsupported_tokens)
    return report


def enforce(
    summary: Summary, ledger: FactLedger, *, retrieved_codings: set[str] | None = None
) -> TraceabilityReport:
    """Fail generation if anything in the summary is untraceable. No partial output."""
    report = check(summary, ledger, retrieved_codings=retrieved_codings)
    if report.ok:
        return report

    problems: list[str] = []
    if report.untraced_lines:
        problems.append(
            f"{len(report.untraced_lines)} line(s) make a clinical claim with no source: "
            + "; ".join(report.untraced_lines[:3])
        )
    if report.dangling_fact_ids:
        problems.append(
            f"{len(report.dangling_fact_ids)} referenced fact id(s) are not in the ledger: "
            + ", ".join(report.dangling_fact_ids[:5])
        )
    if report.unsupported_tokens:
        tokens = ", ".join(sorted({t["token"] for t in report.unsupported_tokens})[:8])
        problems.append(
            f"{len(report.unsupported_tokens)} word(s) in the summary are not supported by "
            f"any recorded fact: {tokens}"
        )

    log.error("summary.traceability_failed", problems=problems)
    raise TraceabilityError(
        "Summary generation failed the traceability check and no summary was produced. "
        + " | ".join(problems)
    )


def with_sources(summary: Summary, ledger: FactLedger) -> list[dict[str, Any]]:
    """Resolve every line's fact ids into what click-to-source renders."""
    by_id = {f.fact_id: f for f in ledger.facts}
    out: list[dict[str, Any]] = []
    for section in summary.sections:
        for line in section.lines:
            sources = []
            for fact_id in line.fact_ids:
                fact = by_id.get(fact_id)
                if fact is None:
                    continue
                span = fact.source
                sources.append(
                    {
                        "factId": fact.fact_id,
                        "tier": fact.tier.value,
                        "confidence": fact.confidence,
                        "verbatim": span.verbatim,
                        "language": span.language,
                        "kind": span.kind,
                        "questionId": getattr(span, "question_id", None),
                        "turnId": getattr(span, "turn_id", None),
                        "modality": getattr(getattr(span, "modality", None), "value", None),
                        "asrConfidence": getattr(span, "asr_confidence", None),
                        "audioRef": getattr(span, "audio_ref", None),
                        "documentId": getattr(span, "document_id", None),
                        "page": getattr(span, "page", None),
                        "bbox": (span.bbox.model_dump() if hasattr(span, "bbox") else None),
                        "handwritten": getattr(span, "handwritten", None),
                    }
                )
            out.append(
                {
                    "sectionId": section.section_id,
                    "text": line.text,
                    "kind": line.kind,
                    "emphasis": line.emphasis,
                    "sources": sources,
                }
            )
    return out


def _line_tokens(line: SummaryLine) -> list[str]:
    return [t.casefold() for t in _TOKEN.findall(line.text)]
