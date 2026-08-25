"""The seeded voice answer goes through the real ASR backend, or admits it did not.

⛔ THE FAILURE THIS PREVENTS IS THE ONE `seed.py` ALREADY COMMITTED ONCE.

Three lab reports were seeded by calling the OCR backend directly and were then described as
having gone "through the actual OCR pipeline". They had not: that path skipped the HTTP route,
the consent gate and the size limit. `test_ocr_has_one_front_door.py` exists because of it.

The voice fixture is the same hazard in a new place. It would have been trivial to write

    SourceEvidence(modality="voice", asr_confidence=0.94, ...)

and call the voice evidence type "seeded". Nothing would have failed, the drawer would have
rendered, and the 0.94 would have been a number nobody measured attached to a clinical fact —
which `Transcript.confidence` documents as fabricated provenance, indistinguishable downstream
from a real score.

So the seed transcribes a committed WAV through `LocalSpeechBackend`, and these tests hold
that line. When no model is configured the confidence must be ABSENT, not invented.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "app" / "modules" / "encounter" / "seed.py"
AUDIO = ROOT / "data" / "fixtures" / "audio"
STEM = "seed_en_voice_stomach"


def test_the_voice_fixture_is_committed() -> None:
    """A fixture that must be regenerated before the seed works is not a fixture."""
    assert (AUDIO / f"{STEM}.wav").exists(), "the seeded voice audio is missing"
    assert (AUDIO / f"{STEM}.json").exists(), "the fixture's manifest is missing"


def test_the_manifest_says_what_is_synthetic_and_what_is_real() -> None:
    """Honesty about a fixture is part of the fixture.

    The audio is macOS `say`, not a patient. Anyone reading a confidence off this must be able
    to see that it says nothing about ASR accuracy on real speakers in a real OPD.
    """
    manifest = json.loads((AUDIO / f"{STEM}.json").read_text(encoding="utf-8"))
    assert manifest["audioIsSynthetic"] is True
    assert "spoken" in manifest and manifest["spoken"].strip()
    assert "accuracy" in manifest["note"].lower(), (
        "the manifest must state that this proves the path, not recognition accuracy"
    )


def test_the_seed_transcribes_rather_than_asserting_a_confidence() -> None:
    """A source scan, because a hardcoded score would look perfectly reasonable.

    `asr_confidence=0.94` in `seed.py` reads like data. Only the absence of a transcribe call
    would reveal that no engine ever saw the audio.
    """
    source = SEED.read_text(encoding="utf-8")
    tree = ast.parse(source)

    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "transcribe" in calls, (
        "seed.py no longer runs the voice fixture through an ASR backend — a seeded voice "
        "confidence that was never measured is fabricated provenance"
    )

    # No numeric literal may be assigned to asr_confidence anywhere in the seed.
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "asr_confidence":
            if isinstance(node.value, ast.Constant) and isinstance(
                node.value.value, (int, float)
            ):
                offenders.append(f"line {node.lineno}: asr_confidence={node.value.value}")
    assert not offenders, "a measured-looking confidence was hardcoded:\n  " + "\n  ".join(
        offenders
    )


def test_absent_recognition_yields_absent_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    """No model must mean `unavailable`, never a substituted number.

    This is the branch a fresh clone actually takes — the Vosk model is a 40 MB download that
    is deliberately not in `requirements.txt` — so it is the branch most likely to rot.
    """
    from app.modules.encounter import seed as S

    class Broken:
        def transcribe(self, *_a, **_kw):  # noqa: ANN002, ANN003
            raise RuntimeError("no model configured")

    monkeypatch.setattr("app.speech.registry.get_speech", lambda: Broken())

    text, confidence, status, _ms = S.transcribe_seed_voice()
    assert confidence is None, "a confidence was invented when no engine was available"
    assert status == "unavailable"
    assert text, "the spoken text is still known from the manifest even without recognition"


@pytest.mark.skipif(
    not (AUDIO / f"{STEM}.json").exists(), reason="fixture manifest absent"
)
def test_a_measured_run_matches_the_recorded_measurement() -> None:
    """When a model IS present, the seed must reproduce the manifest's number.

    Catches a regression in the ASR path that still produces *some* confidence — a resampling
    bug, a changed backend, a model swap — which would otherwise pass silently because the
    field is populated and looks fine.
    """
    manifest = json.loads((AUDIO / f"{STEM}.json").read_text(encoding="utf-8"))
    recorded = manifest.get("asr")
    if not recorded or not recorded.get("measured"):
        pytest.skip("fixture was generated without a model; nothing to compare against")

    from app.modules.encounter import seed as S

    text, confidence, status, _ms = S.transcribe_seed_voice()
    if status != "measured":
        pytest.skip("no ASR model configured in this environment")

    assert text == recorded["text"]
    assert confidence == pytest.approx(recorded["confidence"], abs=1e-6)
