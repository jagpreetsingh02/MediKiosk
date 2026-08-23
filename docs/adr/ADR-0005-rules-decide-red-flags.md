# ADR-0005 — An LLM may propose a red flag; the rules decide

**Context.** Invariant 3 requires emergency detection to be recall-biased and additive. The
question is who decides: a model that has read a lot of medicine, or a rule set a clinician can
read in an afternoon.

**Decision.** The rules decide, always. `data/ontology/redflags.yaml` holds 22 rules in the
same condition DSL the interview uses. `evaluate()` optionally accepts LLM candidates; each is
matched to a real rule id and that rule's own conditions are re-run against the recorded facts.
A candidate naming an unknown rule is logged and discarded — a model cannot invent an
escalation. A rule that already fired is never reconsidered — a model cannot suppress one.

Every proposal is logged whether it fired or not, because a missed escalation is the only
unacceptable error and the record of what was rejected is what makes a miss investigable.

**Alternatives.** LLM-only detection (unauditable, non-reproducible, and it stops working when
the venue wifi dies); rules-only with no LLM (what ships today — the LLM path exists so that a
repeatedly-correct model proposal becomes *evidence that a rule needs widening*, which is a
change a clinician makes to the YAML, not one a model makes at runtime).

**Consequences.** The rules will fire on people who turn out to be fine. That is correct: a
false positive costs a nurse thirty seconds, a false negative is a patient with an evolving MI
sitting in a queue for three hours. Gold scripts therefore also name **forbidden** rules, so
over-triggering is measured rather than accumulating unnoticed.
