# ADR-0001 — `record_fact()` is the only writer, with no bypass

**Context.** The failure that would sink this project is a clinical fact appearing on a
physician's screen that the patient never said. Preventing that by convention — code review,
comments, "be careful" — does not survive contact with a deadline. The SIH 25026 service had
the same problem in a different shape (a hallucinated code in a claim) and solved it with a
single choke point; that pattern is the one worth porting.

**Decision.** Every clinical fact is written by `app/contracts/record.py::record_fact()`, which
refuses six distinct things: no source span, blank verbatim, a null value, a tier that
disagrees with its span class, a path the ontology does not define, and a value that does not
appear in its own source. `ClinicalHistory` is a *projection over the fact ledger*, not a
mutable document, so there is nowhere for an unsourced value to have come from.

Two tests enforce it: one scans the source tree and fails if `Fact(` is constructed anywhere
else, and one fails if `record_fact` ever grows a `force` / `skip_validation` / `trust_me`
parameter.

**Alternatives.** A validation layer at the API edge (covers one edge, and the eval harness
writes facts without going through it); a Pydantic validator on `Fact` (better, but a caller
can still construct one directly with a plausible-looking span).

**Consequences.** Every write path is more verbose, including the ones where the provenance is
obvious. Two features needed a *second kind of evidence* rather than a weakening of the check:
selection evidence for tapped answers (ADR-0003) and closed-vocabulary proof for cross-lingual
extraction (ADR-0004). Both are stricter than the text check they replace, which is the test
of whether an exception is legitimate.
