#!/usr/bin/env python3
"""Generate the seeded voice answer, and measure what ASR actually makes of it.

WHY THIS EXISTS. The demo patient's prior visit was seeded entirely from `touch` evidence,
so the `utterance/voice` evidence type did not exist anywhere in the data — and a
click-to-source drawer that has never rendered a voice segment is a drawer nobody has tested.

WHAT IS REAL AND WHAT IS SYNTHETIC, stated plainly because it matters:

  * The AUDIO is synthetic. macOS `say` reading a line, not a recording of a patient. Real
    speaker variation, accent, and OPD background noise are NOT represented here.
  * The RECOGNITION is real. Vosk, offline, on that exact WAV — the same engine and code
    path `LocalSpeechBackend.transcribe` uses at runtime. The confidence is measured, not
    chosen, and re-running this script reproduces it.

So this fixture proves the voice PATH works end to end. It is not evidence about ASR
accuracy on real speech, and the manifest says so.

    python scripts/make_voice_fixture.py

Requires `say` (macOS) and, to measure, a Vosk model:
    VOSK_MODEL_DIR=~/.cache/medikiosk-models/vosk-model-small-en-us-0.15
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIO = ROOT / "data" / "fixtures" / "audio"

#: The line, and the ontology path it answers. Chosen to match the demo patient's prior
#: visit (a stomach complaint) so the seeded encounter reads as one coherent story rather
#: than a voice fact bolted onto an unrelated history.
SPOKEN = "burning pain in my stomach for about a week"
PATH = "hpi.character"
STEM = "seed_en_voice_stomach"

#: 16 kHz mono LEI16 — what Vosk's acoustic model expects. Feeding it 22050 Hz silently
#: degrades recognition, which would make the measured confidence a fact about the sample
#: rate rather than about the path.
SAMPLE_RATE = 16000


def synthesise(wav: Path) -> None:
    aiff = wav.with_suffix(".aiff")
    subprocess.run(
        ["say", "-v", "Samantha", "-o", str(aiff), SPOKEN], check=True, capture_output=True
    )
    subprocess.run(
        [
            "afconvert",
            "-f", "WAVE",
            "-d", f"LEI16@{SAMPLE_RATE}",
            "-c", "1",
            str(aiff),
            str(wav),
        ],
        check=True,
        capture_output=True,
    )
    aiff.unlink(missing_ok=True)


def measure(wav: Path) -> dict[str, object] | None:
    """Transcribe through the SAME code path the runtime uses. No shortcut."""
    if not os.environ.get("VOSK_MODEL_DIR"):
        return None
    sys.path.insert(0, str(ROOT))
    from app.speech.local import LocalSpeechBackend

    transcript = LocalSpeechBackend().transcribe(
        wav.read_bytes(), language="en", media_type="audio/wav"
    )
    return {
        "text": transcript.text,
        "confidence": transcript.confidence,
        "confidenceStatus": transcript.confidence_status,
        "measured": transcript.measured,
        "reliable": transcript.reliable,
        "durationMs": transcript.duration_ms,
        "backend": transcript.backend,
        "wordConfidences": [list(w) for w in transcript.word_confidences],
    }


def main() -> int:
    AUDIO.mkdir(parents=True, exist_ok=True)
    wav = AUDIO / f"{STEM}.wav"
    synthesise(wav)
    print(f"wrote {wav.relative_to(ROOT)}  ({wav.stat().st_size} bytes)")

    result = measure(wav)
    manifest = {
        "spoken": SPOKEN,
        "path": PATH,
        "audioIsSynthetic": True,
        "recognitionIsReal": result is not None,
        "sampleRate": SAMPLE_RATE,
        "asr": result,
        "note": (
            "Synthetic audio, real recognition. Proves the voice evidence PATH, and says "
            "nothing about ASR accuracy on real speakers in a real OPD."
        ),
    }
    (AUDIO / f"{STEM}.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    if result is None:
        print("NOT MEASURED — set VOSK_MODEL_DIR to record a real confidence.")
    else:
        print(f"  heard      : {result['text']!r}")
        print(f"  confidence : {result['confidence']} ({result['confidenceStatus']})")
        print(f"  matches    : {result['text'] == SPOKEN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
