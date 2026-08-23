# ADR-0004 — Cross-lingual extraction proves itself against the option set

**Context.** A patient says *"mere chhaati mein dard hai"* and the extractor records
`hpi.site = chest`. The text check in `record_fact()` refuses it: `chest` does not appear in
`chhaati`, and it never will. Demanding a textual echo there means demanding that patients
speak English, which for a kiosk built for ten languages is demanding the wrong thing.

**Decision.** `record_fact()` accepts a `coded_value_of` argument: the closed set of option
values the question defines. When it is supplied, the text check is **replaced** — not skipped
— by set membership. The patient's own words remain the span, so the physician still sees
`"chhaati"` under a value that reads `Chest`.

The obligation only applies where it is meaningful. An `open_text` question that also renders
tap options (the chief complaint does) admits free narration, which proves itself the ordinary
way; only a value that genuinely *is* one of the options takes the coded path.

**Alternatives.** Translate the utterance and check against the translation (introduces a
translation step whose errors are invisible, to satisfy a check); store an English gloss on
every span (the same thing, with more storage).

**Consequences.** There are now two proof types and a reviewer must know which applies. The
mitigation is that both are checkable and neither is a flag: you cannot pass `coded_value_of`
without naming a real option set, and the extraction layer derives it from the ontology rather
than accepting it from a caller. `test_closed_vocabulary_proof_still_refuses_a_value_outside_the_set`
pins the tightening.
