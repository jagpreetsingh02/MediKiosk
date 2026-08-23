# ADR-0010 — Offline is the default; the hosted model is the option

**Context.** The brief supplies a Groq key. The natural build uses it everywhere and degrades
if it is missing. The demo is in September, on a venue network, in front of judges.

**Decision.** `LLM_BACKEND=auto` prefers Groq when a key is present, but the **offline
rule-based extractor is the reference implementation** and every published number is measured
on it. The backend is chosen once at startup, never mid-request, so a run cannot silently
switch backends and make its own metrics uninterpretable. The eval harness prints which backend
produced the table.

**Alternatives.** Groq-first with an offline fallback (the fallback is then the untested path,
which is exactly backwards); offline only (gives up on free narration, which is the case a rule
genuinely cannot cover).

**Consequences.** Two extraction implementations to maintain, and the offline one is a phrase
lexicon that needs entries as new phrasings appear. In exchange the demo cannot be broken by a
network, and "does the LLM actually help?" is answerable by running the same harness twice
instead of by assertion.

Three things this decision paid for that were not anticipated:

1. **The model named in the brief no longer exists.** `llama-3.3-70b-versatile` has been
   decommissioned by Groq and the API 404s. Nothing broke, because nothing load-bearing was
   pointed at it.
2. **A real rate-limit found a real bug.** Running the harness against Groq produced 429s,
   which surfaced that an unreachable model returned a 503 to the *patient* rather than
   degrading to touch. The deterministic spine was supposed to cover exactly that case and did
   not, until this run proved it.
3. **The comparison is measurable rather than assumed** — `docs/EVALUATION.md` reports both.
