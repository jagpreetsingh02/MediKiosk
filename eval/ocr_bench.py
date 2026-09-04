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
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.errors import SwastraError
from app.modules.dialogue.ontology import load_ontology
from app.modules.documents.backends import get_ocr_backend
from app.modules.documents.entities import extract_entities

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
    details: dict[str, Any] = field(default_factory=dict)


def _norm(text: str) -> str:
    return "".join(c for c in text.casefold() if c.isalnum())


def score_one(backend_name: str, path: Path, truth: dict) -> Score:
    variant = (
        "degraded"
        if "_degraded" in path.stem
        else "scan"
        if "_scan" in path.stem
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
    except SwastraError as exc:
        score.ok = False
        score.error = str(exc)[:120]
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

    score.details = {
        "medicationsFound": [e.text for e in got_meds],
        "investigationsFound": [e.text for e in got_inv],
        "needsVerification": len(needs_check),
    }
    return score


def run() -> list[Score]:
    load_ontology()  # fail fast if the ontology is broken
    scores: list[Score] = []
    for truth_path in sorted(FIXTURES.glob("*.truth.json")):
        base = truth_path.name.removesuffix(".truth.json")
        truth = json.loads(truth_path.read_text())
        for suffix in (".pdf", "_scan.png", "_degraded.png"):
            path = FIXTURES / f"{base}{suffix}"
            if not path.exists():
                continue
            for backend in ("textlayer", "tesseract"):
                scores.append(score_one(backend, path, truth))
    return scores


def render(scores: list[Score]) -> str:
    lines = [
        "| backend | fixture | variant | ents | med recall | dose acc | inv recall | flag acc "
        "| dx recall | mean conf | to human |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in scores:
        if not s.ok:
            lines.append(
                f"| {s.backend} | {s.fixture} | {s.variant} | — | — | — | — | — | — | — | "
                f"_{s.error}_ |"
            )
            continue
        lines.append(
            f"| {s.backend} | {s.fixture} | {s.variant} | {s.entities_found} "
            f"| {s.med_recall:.2f} | {s.med_dose_accuracy:.2f} | {s.inv_recall:.2f} "
            f"| {s.inv_flag_accuracy:.2f} | {s.dx_recall:.2f} | {s.mean_confidence:.2f} "
            f"| {s.verification_rate:.0%} |"
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
