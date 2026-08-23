# ADR-0007 — Untranslated questions fall back to English, visibly

**Context.** The kiosk offers ten languages. Every question carries English and Hindi. Writing
clinically accurate, low-literacy-appropriate phrasing in the other eight requires speakers of
those languages, and I am not one.

**Decision.** A question with no prompt in the session language falls back to English, and the
API sets `translationMissing: true` on that question. The kiosk renders a visible line saying
the question is not yet translated. The language picker also marks which languages have a full
question set before the patient commits to one.

**Alternatives.** Machine-translate the ontology at build time (produces clinical phrasing
nobody has checked, in a context where a mistranslated allergy question is dangerous); ship
only English and Hindi (the language list is part of the problem statement, and the option
labels, consent audio and degradation prompts genuinely are translated further); fall back
silently (the patient discovers it three questions in, having already chosen).

**Consequences.** A Tamil-speaking patient sees Tamil in the language picker, Tamil consent
audio and Tamil degradation prompts, but English question text with a notice. That is worse
than full Tamil and much better than a fabricated translation.

The fix is not a code change: add `ta:` keys to `data/ontology/*.yaml` and the flag stops
appearing. The structure is ready for translators; the translations are the gap, and they are
reported as one rather than papered over.
