"""The same brief, regrouped for the person it is about.

SAME PAYLOAD, DIFFERENT GROUPING — and that is the design, not a shortcut. The patient view is
derived from the clinician payload by a pure function, so the two can never disagree about
what is on the record. A separately-assembled patient report would be a second source of truth
about someone's own health, and the first time the two drifted, the patient would be the one
who could not tell.

It is regrouped by WHERE THE INFORMATION CAME FROM, because that is the question a patient
actually has, and it is the one the system can answer honestly:

    What you told us                  their own words, this visit
    What came from your documents     read off a page they handed over
    What comes from your previous visits
    Items still waiting for doctor verification

WHAT IS REMOVED, DELIBERATELY:

  * internal identifiers — `factRef`, `evidenceIds`, `encounterRef`, paths like `hpi.timing`
  * `state` and `tier` — "document tier, confirmed state" is our vocabulary, not theirs
  * confidence numbers — "0.94" invites a patient to reason about a number whose scale nobody
    explained to them, and the honest summary of a low-confidence reading is that a person
    still needs to check it, which is what the fourth group says in words
  * FHIR anything

WHAT IS NOT REMOVED: the fact that something is unverified. Softening that would be the one
edit that makes this view dangerous rather than merely gentler.
"""

from __future__ import annotations

from typing import Any

#: Paths whose label is our internal vocabulary. Anything not here is shown with the label
#: the clinician view already gave it, which is written in plain words to begin with.
PLAIN_LABELS: dict[str, str] = {
    "chief_complaint.text": "What brought you in",
    "chief_complaint.duration": "How long you have had it",
    "hpi.onset": "How it started",
    "hpi.severity": "How bad it feels",
    "hpi.site": "Where it is",
    "hpi.character": "What it feels like",
    "hpi.timing": "When it happens",
    "hpi.exacerbating": "What makes it worse",
    "hpi.relieving": "What makes it better",
    "hpi.associated": "Other things you noticed",
    "drug_allergy.has_allergy": "Allergies to medicines",
    "drug_allergy.substances": "Medicines you react to",
    "drug_allergy.reaction": "What happens when you react",
    "drug_allergy.taking_medicines": "Medicines you are taking",
}


def _label(item: dict[str, Any]) -> str:
    return PLAIN_LABELS.get(item.get("path", ""), item.get("label") or "")


def _plain(item: dict[str, Any]) -> dict[str, Any]:
    """One line, stripped of everything that is ours rather than theirs."""
    return {
        "label": _label(item),
        "value": item.get("displayValue") or item.get("value"),
    }


def to_patient_view(payload: dict[str, Any]) -> dict[str, Any]:
    """Regroup a clinician brief for the patient. Pure — same input, same output."""
    told_us: list[dict[str, Any]] = []
    from_documents: list[dict[str, Any]] = []
    awaiting: list[dict[str, Any]] = []

    snapshot = payload.get("snapshot", {})
    for item in list(snapshot.get("items", [])) + list(snapshot.get("allergies", [])):
        line = _plain(item)
        if not line["value"]:
            continue
        kinds = item.get("evidenceKinds") or []
        if "document" in kinds:
            from_documents.append(line)
        else:
            told_us.append(line)
        # Unverified is stated, never softened away. A patient who does not know a reading is
        # unchecked cannot ask anyone to check it.
        if not item.get("confirmedByPhysician"):
            awaiting.append(line)

    # Medicines read off a page they handed over.
    for group in snapshot.get("reportedMedications", []):
        parts = [group.get("name"), group.get("dose"), group.get("frequency")]
        text = " ".join(str(p) for p in parts if p)
        if text:
            from_documents.append({"label": "Medicine on your prescription", "value": text})

    # Previous visits: what the record already held before today.
    previous: list[dict[str, Any]] = []
    for med in payload.get("medications", {}).get("items", []):
        if med.get("origin") != "previous-visit":
            continue
        text = " ".join(str(p) for p in [med.get("name"), med.get("dose")] if p)
        if text:
            previous.append({"label": "Medicine from an earlier visit", "value": text})
    for series in payload.get("observations", {}).get("series", []):
        points = series.get("points", [])
        if len(points) < 2:
            continue
        first, last = points[0], points[-1]
        previous.append(
            {
                "label": f"{series.get('display')} over time",
                # Two recorded numbers and their dates. No word about what the change means.
                "value": (
                    f"{first.get('value')} on {first.get('observedOn')}, "
                    f"{last.get('value')} on {last.get('observedOn')}"
                ),
            }
        )

    changed = payload.get("whatChanged", {})
    if changed.get("comparedWith"):
        previous.append(
            {
                "label": "Compared with your last visit",
                "value": (
                    f"{len(changed.get('new', []))} new thing(s) recorded, "
                    f"{len(changed.get('persisting', []))} the same as before"
                ),
            }
        )

    return {
        "reportVersion": payload.get("reportVersion"),
        "audience": "patient",
        "forWhom": payload.get("header", {}).get("displayName"),
        "groups": [
            {
                "title": "What you told us",
                "items": told_us,
                "emptyReason": None if told_us else "You have not told us anything yet today.",
            },
            {
                "title": "What came from your documents",
                "items": from_documents,
                "emptyReason": None
                if from_documents
                else "You have not shown us any papers yet.",
            },
            {
                "title": "What comes from your previous visits",
                "items": previous,
                "emptyReason": None
                if previous
                else "This is the first visit we have a record of.",
            },
            {
                "title": "Items still waiting for doctor verification",
                "items": awaiting,
                "emptyReason": None
                if awaiting
                else "The doctor has checked everything here.",
            },
        ],
        "notice": (
            "This is what we have written down about your visit. It is not a diagnosis, and "
            "it does not tell you what is wrong — your doctor will talk to you about that."
        ),
    }
