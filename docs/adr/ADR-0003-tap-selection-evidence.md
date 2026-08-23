# ADR-0003 — A tap proves itself by selection, not by text

**Context.** Wiring up tapped answers, `record_fact()` refused this:

```
path  hpi.associated
value ["sweating", "breathlessness"]
span  "Cold sweating, Trouble breathing"   <- the labels the patient pressed
```

`sweating` appears in "Cold sweating", but `breathlessness` does not appear in "Trouble
breathing". The guard was right — the recorded value genuinely did not appear in its own
source — and the tempting fix was to loosen the text check.

**Decision.** Loosening it would have weakened the anti-paraphrase check for *every* fact in
the system to fix a case that is not a paraphrase at all. Instead, `UtteranceSpan` gained
`selected_values`: the exact option values the kiosk rendered and the patient pressed. When a
span carries them, the recorded value must be a member — an exact set-membership test rather
than a substring search.

`verbatim` still holds the human label, so click-to-source shows the physician the words the
patient actually read.

**Alternatives.** Record the label as the value (breaks the condition DSL, which branches on
option keys); store both and reconcile at render time (two sources of truth for one answer).

**Consequences.** "The patient pressed the button whose value is `breathlessness`" is stronger
evidence than any substring match, so this is a tightening. A validator enforces that
`selected_values` can only accompany `modality=touch`, which stops it becoming a general
escape hatch. Same reasoning, different mechanism, in ADR-0004.
