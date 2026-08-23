# ADR-0006 — `ClinicalHistory` is a projection, and contradictions are preserved

**Context.** The obvious model is a `ClinicalHistory` object that the dialogue fills in as it
goes. It is also the model that makes Invariant 2 impossible to hold: a mutable document is one
careless `history.hpi.site = "chest"` away from an unsourced field, forever.

**Decision.** The fact ledger is the primary store and the history is a pure function of it
(`app/contracts/projection.py`). Run it twice on the same ledger and you get the same history;
run it on an empty ledger and every slot is honestly `not_asked`.

The ledger is append-only. When a patient contradicts themselves the earlier fact is marked
`superseded_by` rather than removed, and the slot renders the latest value with the earlier one
listed underneath.

**Alternatives.** Mutable document with a provenance side-table (the two drift, and the drift is
silent); event sourcing with full replay (this is that, minus the machinery nobody needs here).

**Consequences.** Every read is a rebuild. That is free at this scale — a session holds tens of
facts, and the whole projection plus summary assembly plus the traceability check runs in about
a millisecond.

The contradiction behaviour is the part worth defending: it looks like clutter and it is not.
"Three days" then "about a week" is clinically interesting, and a physician cannot weigh it if
the first answer was overwritten. `Slot.superseded` is why the screen can show both.
