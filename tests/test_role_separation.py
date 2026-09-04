"""The patient's surface and the doctor's surface are separate, and this is what keeps them so.

⛔ THE FAILURE THIS PREVENTS IS NOT HYPOTHETICAL. `PatientPortal.tsx` reached into
`physician/` for its timeline, its medication thread and its evidence drawer, because those
three components already rendered the right data and were sitting right there. Nothing broke
that day. What it meant was that the patient's screen was one prop away from any control a
future edit added to a physician component — a verification button, a commit affordance, a
"needs reconciliation" chip written for somebody reading *about* a patient — and nothing in
the build would have said so. That chip did in fact appear on the patient screen, and it took
a human reading the rendered page to notice.

So the rule is structural rather than a matter of care:

    patient/ and physician/ never import from each other.

    physician/ never imports from kiosk/ either, because the kiosk IS the patient surface —
    it is the patient's device, sitting behind the Patient door — so borrowing a screen from
    it is the same mistake with a different folder name.

    What both roles genuinely need lives in record/, which imports from neither, and varies
    its wording (never its content) through an explicit `audience` prop.

This is a source scan for the same reason `test_ocr_has_one_front_door.py` is: the bug is not
a call that behaves wrongly, it is a call that behaves correctly today while removing the
guarantee that it will keep doing so tomorrow. Only the import graph shows that.

See ADR-0016.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"

#: Every `import … from '<specifier>'` and `export … from '<specifier>'` in a file.
_IMPORT = re.compile(r"""(?:import|export)[^;]*?\sfrom\s+['"]([^'"]+)['"]""", re.S)


def _imports(path: Path) -> list[str]:
    return _IMPORT.findall(path.read_text(encoding="utf-8"))


def _sources(folder: str) -> list[Path]:
    found = sorted((SRC / folder).glob("*.tsx")) + sorted((SRC / folder).glob("*.ts"))
    assert found, f"frontend/src/{folder}/ has no sources — has it been renamed?"
    return found


def _offences(folder: str, forbidden: tuple[str, ...]) -> list[str]:
    out = []
    for path in _sources(folder):
        for specifier in _imports(path):
            if any(specifier.startswith(f"../{bad}/") for bad in forbidden):
                out.append(f"{path.relative_to(SRC)} imports {specifier}")
    return out


def test_the_patient_surface_does_not_import_the_doctors() -> None:
    assert _offences("patient", ("physician",)) == [], (
        "A patient screen is importing a component owned by the physician workspace. If both "
        "roles need it, move it to frontend/src/record/ — which is owned by neither and may "
        "vary only its wording, through `audience`. See ADR-0016."
    )


def test_the_doctors_surface_does_not_import_the_patients() -> None:
    assert _offences("physician", ("patient", "kiosk")) == [], (
        "The doctor's workspace is importing from the patient's surface (`patient/` is their "
        "record, `kiosk/` is their device). Move the shared piece to frontend/src/record/. "
        "See ADR-0016."
    )


def test_the_shared_record_views_belong_to_neither_role() -> None:
    """`record/` is the neutral ground, and neutral means it depends on neither side."""
    assert _offences("record", ("patient", "physician", "kiosk")) == [], (
        "frontend/src/record/ imported from a role folder. It is the ground both roles stand "
        "on; a dependency in that direction makes it one role's code that the other borrows, "
        "which is exactly what it exists to stop."
    )


def test_the_three_shared_views_actually_live_in_record() -> None:
    """Named explicitly, so 'move it back and update the imports' is not a green build."""
    for name in ("LongitudinalTimeline.tsx", "MedicationHistory.tsx", "EvidenceDrawer.tsx"):
        assert (SRC / "record" / name).exists(), (
            f"{name} is read by BOTH the patient and the doctor. It belongs in "
            f"frontend/src/record/, not in either role's folder."
        )


def test_the_front_door_offers_both_workflows() -> None:
    """The first screen is the fork. If it stops being one, the split is decorative."""
    hero = (SRC / "hero" / "Hero.tsx").read_text(encoding="utf-8")
    assert 'to="/patient"' in hero, "The hero no longer offers the patient a way in."
    assert 'to="/doctor"' in hero, "The hero no longer offers the doctor a way in."

    main = (SRC / "main.tsx").read_text(encoding="utf-8")
    for route in ('path="/patient"', 'path="/doctor"'):
        assert route in main, f"No route for {route} — the front door leads nowhere."
    # The demo launcher deep-links `/physician?session=…`. A redirect would drop the query,
    # so the original path stays mounted rather than forwarding.
    assert 'path="/physician"' in main, (
        "The original /physician path was removed. The demo launcher deep-links it with "
        "?session=, and a redirect drops the query string."
    )


def test_medication_history_says_reconciliation_only_to_a_clinician() -> None:
    """The one place the shared views differ by audience, and the reason the prop exists.

    "Needs reconciliation" is a sentence about a medicines list, written for somebody reading
    about a patient. It is not softened away for the patient — the finding is shown either
    way — it is said in words that are about them rather than about their chart.
    """
    source = (SRC / "record" / "MedicationHistory.tsx").read_text(encoding="utf-8")
    assert "audience" in source, "MedicationHistory lost its audience prop."
    assert "Needs reconciliation" in source
    assert "patient ?" in source, (
        "MedicationHistory no longer switches its wording on audience, so clinician "
        "vocabulary reaches the patient's own screen."
    )
