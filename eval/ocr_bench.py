"""Benchmark the OCR backends against ground truth. `python -m eval.ocr_bench`.

This exists so the choice of OCR engine is a measurement rather than an argument. It reports,
per backend and per fixture class:

* **entity recall** — of the medications / investigations / diagnoses in the truth file, how
  many did the pipeline find?
* **dose accuracy** — of the medications found, how many carried the right dose? A drug name
  without its dose is not clinically useful, and a *wrong* dose is dangerous.
* **mean OCR confidence** and **verification-lane rate** — what fraction of entities the
  backend pushed to a human. High is not automatically bad: on a degraded scan, pushing
  everything to a human is the *correct* behaviour.

And, since the handwriting lane exists, two more that matter more than any of the above:

* **name resolution** — of the medicines on the page, how many did the constrained matcher
  identify by name? This is the number the feature is *for*: raw characters are not the
  product, an understandable medicine name is.
* **confidently wrong** — how many medicines were presented with `needsVerification: false`
  and a name that is not the right one. **This must be zero.** Every other number here is a
  quality measure and this one is a safety measure: a medicine the system got wrong while
  telling a patient it was sure is the failure the entire design exists to prevent, and it is
  not traded off against recall at any exchange rate.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.errors import MediKioskError
from app.modules.dialogue.ontology import load_ontology
from app.modules.documents.backends import get_ocr_backend
from app.modules.documents.entities import extract_entities
from app.modules.documents.prescription import interpret

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "documents"

MEDIA_TYPES = {".pdf": "application/pdf", ".png": "image/png", ".txt": "text/plain"}


@dataclass
class Score:
    backend: str
    fixture: str
    variant: str
    ok: bool = True
    error: str | None = None
    entities_found: int = 0
    med_recall: float = 0.0
    med_dose_accuracy: float = 0.0
    inv_recall: float = 0.0
    inv_flag_accuracy: float = 0.0
    dx_recall: float = 0.0
    mean_confidence: float = 0.0
    verification_rate: float = 0.0
    #: Of the medicines on the page, how many did the constrained matcher name?
    name_resolution: float = 0.0
    #: Presented as certain, and wrong. The only number here with a hard bound.
    confidently_wrong: int = 0
    details: dict[str, Any] = field(default_factory=dict)


def _norm(text: str) -> str:
    return "".join(c for c in text.casefold() if c.isalnum())


def _one_line(exc: Exception) -> str:
    """A failure reason that fits in a table cell.

    Hugging Face's gated-repo error is four lines long with a URL in the middle of it, which
    turned one unavailable engine into a broken markdown table and a report nobody could read.
    """
    return " ".join(str(exc).split())[:110]


def score_one(backend_name: str, path: Path, truth: dict) -> Score:
    variant = (
        "degraded"
        if "_degraded" in path.stem
        else "scan"
        if "_scan" in path.stem
        else "handwritten"
        if "handwritten" in path.stem
        else path.suffix.lstrip(".")
    )
    score = Score(backend=backend_name, fixture=path.stem.split("_")[0], variant=variant)

    try:
        backend = get_ocr_backend(backend_name)
        data = path.read_bytes()
        result = backend.read(
            data, filename=path.name, media_type=MEDIA_TYPES.get(path.suffix, "application/pdf")
        )
        confident, needs_check = extract_entities(result, sex="female")
    except MediKioskError as exc:
        score.ok = False
        score.error = _one_line(exc)
        return score

    everything = confident + needs_check
    score.entities_found = len(everything)
    score.mean_confidence = round(result.mean_confidence, 4)
    score.verification_rate = round(len(needs_check) / len(everything), 4) if everything else 0.0

    # --- medications ---
    want_meds = truth.get("medications", [])
    got_meds = [e for e in everything if e.kind == "medication"]
    matched_meds = []
    for want in want_meds:
        for got in got_meds:
            if _norm(want["name"])[:6] and _norm(want["name"])[:6] in _norm(got.text):
                matched_meds.append((want, got))
                break
    score.med_recall = round(len(matched_meds) / len(want_meds), 4) if want_meds else 1.0
    dose_hits = sum(
        1
        for want, got in matched_meds
        if _norm(want["dose"]) == _norm(str(got.detail.get("dose") or ""))
    )
    score.med_dose_accuracy = (
        round(dose_hits / len(matched_meds), 4) if matched_meds else (1.0 if not want_meds else 0.0)
    )

    # --- investigations ---
    want_inv = truth.get("investigations", [])
    got_inv = [e for e in everything if e.kind == "investigation"]
    matched_inv = []
    for want in want_inv:
        for got in got_inv:
            if _norm(want["analyte"])[:5] in _norm(got.text):
                matched_inv.append((want, got))
                break
    score.inv_recall = round(len(matched_inv) / len(want_inv), 4) if want_inv else 1.0
    flag_hits = sum(1 for want, got in matched_inv if want["flag"] == got.detail.get("rangeFlag"))
    score.inv_flag_accuracy = (
        round(flag_hits / len(matched_inv), 4) if matched_inv else (1.0 if not want_inv else 0.0)
    )

    # --- diagnoses ---
    want_dx = truth.get("diagnoses", [])
    got_dx = [e for e in everything if e.kind == "diagnosis"]
    dx_hits = sum(
        1 for want in want_dx if any(_norm(want)[:12] in _norm(got.text) for got in got_dx)
    )
    score.dx_recall = round(dx_hits / len(want_dx), 4) if want_dx else 1.0

    # --- the interpretation layer -------------------------------------------------------
    #
    # Scored against the CANONICAL names in the truth file, not against what the page says.
    # "Augmtin" is what is written; "Augmentin" is what it is. The gap between those two
    # columns is the entire job of `prescription.py`, and scoring against the wrong one would
    # award marks for transcription and none for understanding.
    reading = interpret(result)
    wanted = [_norm(want["name"]) for want in want_meds]
    resolved = [
        _norm(str(med.medication_name))
        for med in reading.medications
        if med.medication_name
    ]
    named = sum(1 for want in wanted if any(want[:6] and want[:6] in got for got in resolved))
    score.name_resolution = round(named / len(wanted), 4) if wanted else 1.0

    # Confidently wrong: stated without a human, and not one of the medicines on the page.
    score.confidently_wrong = sum(
        1
        for med in reading.medications
        if not med.needs_verification
        and med.medication_name
        and not any(want[:6] and want[:6] in _norm(str(med.medication_name)) for want in wanted)
    )

    score.details = {
        "medicationsFound": [e.text for e in got_meds],
        "investigationsFound": [e.text for e in got_inv],
        "needsVerification": len(needs_check),
        "interpreted": [
            {
                "raw": med.raw_text,
                "read": med.sentence(),
                "needsVerification": med.needs_verification,
            }
            for med in reading.medications
        ],
    }
    return score


#: Every engine, on every fixture it can read. `trocr` is included even when it is not
#: installed: a row reading "unavailable" is a *result* — it is the state a kiosk without the
#: optional dependencies is in, and hiding it would make the report describe a machine nobody
#: is running on.
BACKENDS = ("textlayer", "tesseract", "trocr")
SUFFIXES = (".pdf", "_scan.png", "_degraded.png", ".png")


def run() -> list[Score]:
    load_ontology()  # fail fast if the ontology is broken
    scores: list[Score] = []
    for truth_path in sorted(FIXTURES.glob("*.truth.json")):
        base = truth_path.name.removesuffix(".truth.json")
        truth = json.loads(truth_path.read_text())
        for suffix in SUFFIXES:
            path = FIXTURES / f"{base}{suffix}"
            if not path.exists():
                continue
            for backend in BACKENDS:
                engine = get_ocr_backend(backend)
                if not engine.available:
                    scores.append(
                        Score(
                            backend=backend,
                            fixture=base.split("_")[0],
                            variant=suffix.strip("._").replace(".png", ""),
                            ok=False,
                            error="not installed on this machine",
                        )
                    )
                    continue
                scores.append(score_one(backend, path, truth))
    return scores


def render(scores: list[Score]) -> str:
    lines = [
        "| backend | fixture | variant | ents | med recall | dose acc | named | inv recall "
        "| flag acc | dx recall | mean conf | to human | CONFIDENTLY WRONG |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in scores:
        if not s.ok:
            lines.append(
                f"| {s.backend} | {s.fixture} | {s.variant} | — | — | — | — | — | — | — | — "
                f"| — | _{s.error}_ |"
            )
            continue
        lines.append(
            f"| {s.backend} | {s.fixture} | {s.variant} | {s.entities_found} "
            f"| {s.med_recall:.2f} | {s.med_dose_accuracy:.2f} | {s.name_resolution:.2f} "
            f"| {s.inv_recall:.2f} | {s.inv_flag_accuracy:.2f} | {s.dx_recall:.2f} "
            f"| {s.mean_confidence:.2f} | {s.verification_rate:.0%} "
            f"| **{s.confidently_wrong}** |"
        )
    wrong = sum(s.confidently_wrong for s in scores if s.ok)
    lines.append("")
    lines.append(
        f"**Confidently wrong across every engine and every fixture: {wrong}.** "
        "This is the number with a hard bound; the rest are quality measures."
        if wrong == 0
        else f"**⚠ {wrong} medicines were presented as certain and were wrong.** "
        "Nothing else in this table matters until that is zero."
    )
    return "\n".join(lines)


def main() -> int:
    scores = run()
    print(render(scores))
    out = Path(__file__).resolve().parents[1] / "eval" / "reports" / "ocr_bench.json"
    out.write_text(json.dumps([s.__dict__ for s in scores], indent=2, default=str) + "\n")
    print(f"\nwrote {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
