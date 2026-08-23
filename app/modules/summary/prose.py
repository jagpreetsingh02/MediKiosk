"""Optional LLM prose smoothing — the LLM's second and last job in the whole system.

What it may do: turn a section's bullet lines into one or two flowing sentences.
What it may not do: introduce a single token that no recorded fact supports.

The enforcement is not a prompt instruction. Smoothed prose is run through the *same*
traceability token check as the template output, and if it introduces an unsupported word the
smoothed version is **discarded and the deterministic bullets are kept**. The model gets one
attempt and no negotiation.

This is why smoothing is safe to offer at all, and it is worth being clear about the trade:
smoothing makes the summary nicer to read and adds a failure mode. The failure mode is
contained to "the physician sees bullets instead of a sentence", which is not a clinical risk.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.audit.chain import prompt_fingerprint
from app.core.errors import LLMContractError
from app.core.logging import get_logger
from app.llm.protocol import LLMResponse, parse_or_fail
from app.llm.registry import get_llm
from app.llm.schemas import SmoothedSection
from app.modules.summary.assemble import Summary, SummaryLine, SummarySection
from app.modules.summary.traceability import (
    STOPWORDS,
    TEMPLATE_VOCABULARY,
    _authored_vocabulary,
    _supported_vocabulary,
    _TOKEN,
)

log = get_logger(__name__)

SMOOTHING_SYSTEM = """You rewrite a list of clinical facts as one short paragraph.

Absolute constraints:
- Use ONLY the words and facts given. Do not add a symptom, a qualifier, a severity, a
  duration, an anatomical term or a mechanism that is not already present.
- Do NOT interpret. Do not name a disease. Do not suggest a cause. Do not say what is likely.
- Do not add "consistent with", "suggestive of", "concerning for", or any similar phrase.
- Keep it under 60 words. Plain clinical register, past tense, third person.
- If you cannot rewrite it without adding anything, return the facts joined by semicolons."""

#: Sections where smoothing helps a reader. Escalation and gaps are deliberately excluded:
#: a red flag must read identically every time, and a list of gaps is a list.
SMOOTHABLE = frozenset({"hpi", "past_medical", "personal_history", "review_of_systems"})


@dataclass(slots=True)
class SmoothingOutcome:
    section_id: str
    applied: bool
    reason: str | None = None
    unsupported_tokens: list[str] | None = None
    response: LLMResponse | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sectionId": self.section_id,
            "applied": self.applied,
            "reason": self.reason,
            "unsupportedTokens": self.unsupported_tokens,
        }


def smooth(
    summary: Summary, ledger: Any, *, sections: set[str] | None = None
) -> tuple[Summary, list[SmoothingOutcome]]:
    """Attempt to smooth each eligible section. Silently keeps bullets where it cannot."""
    backend = get_llm()
    outcomes: list[SmoothingOutcome] = []

    if backend.offline:
        # The rule-based backend has no prose capability and will not pretend to. Bullets
        # are the correct output here, not a degraded one.
        return summary, [
            SmoothingOutcome(
                section_id="*", applied=False,
                reason="The offline backend does not generate prose; template output kept.",
            )
        ]

    allowed = (sections or SMOOTHABLE) & SMOOTHABLE
    supported = (
        _supported_vocabulary(ledger)
        | TEMPLATE_VOCABULARY
        | STOPWORDS
        | _authored_vocabulary()
    )

    for section in summary.sections:
        if section.section_id not in allowed:
            continue
        fact_lines = [line for line in section.lines if line.kind == "fact"]
        if len(fact_lines) < 3:
            outcomes.append(
                SmoothingOutcome(section.section_id, False, "Too few lines to be worth smoothing.")
            )
            continue

        outcome = _smooth_section(section, fact_lines, supported, backend)
        outcomes.append(outcome)

    return summary, outcomes


def _smooth_section(
    section: SummarySection,
    fact_lines: list[SummaryLine],
    supported: set[str],
    backend: Any,
) -> SmoothingOutcome:
    user = "\n".join(f"- {line.text}" for line in fact_lines)
    try:
        response = backend.complete(
            system=SMOOTHING_SYSTEM,
            user=f"Section: {section.title}\n\nFacts:\n{user}",
            schema_hint='{"prose": "<one short paragraph>"}',
        )
        smoothed = parse_or_fail(response, SmoothedSection)
    except LLMContractError as exc:
        return SmoothingOutcome(section.section_id, False, f"Contract failure: {exc}"[:160])
    except Exception as exc:  # an unreachable model must not lose the summary
        return SmoothingOutcome(section.section_id, False, f"Backend error: {exc}"[:160])

    unsupported = sorted(
        {
            token for token in _TOKEN.findall(smoothed.prose)
            if token.casefold() not in supported and not token.isnumeric()
        }
    )
    if unsupported:
        log.warning(
            "summary.smoothing_rejected",
            section=section.section_id, tokens=unsupported[:8],
        )
        return SmoothingOutcome(
            section.section_id, False,
            "Smoothed prose introduced words no recorded fact supports; bullets kept.",
            unsupported_tokens=unsupported,
            response=response,
        )

    # Accepted. The prose line inherits the union of every fact id it summarises, so
    # click-to-source on the paragraph shows all of them.
    all_ids = sorted({fid for line in fact_lines for fid in line.fact_ids})
    section.lines = [
        SummaryLine(text=smoothed.prose, fact_ids=all_ids, kind="fact", tier="mixed")
    ] + [line for line in section.lines if line.kind != "fact"]

    log.info(
        "summary.smoothed",
        section=section.section_id, model=response.model_name,
        prompt_hash=prompt_fingerprint(response.prompt)[:12],
    )
    return SmoothingOutcome(section.section_id, True, None, response=response)
