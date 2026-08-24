# ADR-0012 — A named human's reading of an OCR span is evidence, not a bypass

**Context.** `record_fact()` refuses a fact whose value does not appear in its own source span
(Invariant 2, the anti-paraphrase check). Document verification produced exactly that shape: a
verifier reads "TAB. METFARMIN 500mg", says it is Metformin, and the system tries to record
`Metformin` against a span that does not contain the string "Metformin".

The check did its job and refused. `_record_entity` caught the exception and logged it. So the
verification lane accepted corrections, reported success, recorded a fact ID count of zero,
and dropped every correction that actually changed a word — which is most of them, since a
correction that changes nothing is not a correction. The test covering this read `if facts:`
and therefore passed either way.

**Decision.** Add `human_reading` and `read_by` to `DocumentSpan`, and let `_value_is_echoed()`
accept an echo in the reading as well as the verbatim. The model refuses a `human_reading` with
no `read_by`.

The framing matters. This is **not** a relaxation of the echo check — it is a second kind of
evidence, admitted on the same terms as the first. "A person named Dr Mehta read this scrawl as
Metformin" is a provenance claim that can be shown to a later reviewer, audited, and
disagreed with. "Someone typed Metformin" is not, which is why the unattributed case raises.
The scrawl stays in `verbatim`; the reading sits beside it, and the evidence drawer shows both.

**Alternatives.** Record the correction as a fresh fact with the corrected text as its own span
(fabricates a document span that does not exist on the page, and loses the scrawl — the exact
thing a physician needs to see). Store corrections outside the ledger (creates a second,
unvalidated write path, which is what Invariant 2 exists to prevent). Relax `_value_is_echoed`
for document-tier facts (opens the paraphrase hole for *un*verified OCR too, which is the
larger risk).

**Consequences.** A correction can still not launder an arbitrary value in: the value must echo
in the reading, so "Metformin" backed by a reading of "Metformin" is accepted and "Warfarin" is
not. There is now one more field on the span that the FHIR mapping and the evidence drawer both
have to know about. `tests/test_document_review.py` pins all four behaviours, including the
pre-existing refusal, so the fix cannot be widened by accident later.
