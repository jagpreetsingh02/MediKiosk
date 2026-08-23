"""The offline speech backend. Ships first, so the demo never depends on a network.

ASR: Vosk when a model directory is configured (`VOSK_MODEL_DIR`), which gives genuine
offline recognition for Hindi and English. When it is not configured — the default, because a
Vosk model is a 50 MB download nobody should need to clone this repo — ASR falls back to the
*client* path: the browser's Web Speech API runs on the kiosk device and posts its transcript
and confidence here. That is still offline in the sense that matters (no key, no vendor, works
when the venue wifi dies), and it is what the shipped kiosk actually uses.

TTS: `say` on macOS, `espeak-ng` where present, otherwise a signal to the client to use
`speechSynthesis`. Every path produces audible output on the machines this will be demoed on.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

from app.core.config import settings
from app.core.errors import UpstreamUnavailable
from app.core.logging import get_logger
from app.speech.protocol import Transcript, Utterance

log = get_logger(__name__)

#: macOS voices that exist on a stock install. Hindi is present on recent macOS.
_MAC_VOICES = {"hi": "Lekha", "en": "Samantha", "ta": "Vani", "bn": "Samantha"}


class LocalSpeechBackend:
    """Satisfies `SpeechBackend`."""

    name = "local"
    offline = True
    languages: tuple[str, ...] = ("en", "hi", "bn", "ta", "te", "mr", "kn", "ml", "gu", "pa")

    def __init__(self) -> None:
        self._vosk_model = None
        self._vosk_dir = settings.vosk_model_dir

    # -------------------------------------------------------------- ASR

    def _load_vosk(self):
        if self._vosk_model is not None or not self._vosk_dir:
            return self._vosk_model
        try:
            from vosk import Model  # type: ignore[import-not-found]

            self._vosk_model = Model(self._vosk_dir)
            log.info("speech.vosk_loaded", path=self._vosk_dir)
        except Exception as exc:
            log.warning("speech.vosk_unavailable", error=str(exc)[:160])
            self._vosk_dir = None
        return self._vosk_model

    def transcribe(self, audio: bytes, *, language: str, media_type: str) -> Transcript:
        model = self._load_vosk()
        if model is None:
            # No server-side ASR configured. The kiosk client does recognition on-device
            # and posts the result to /dialogue/answer directly; this path exists for the
            # eval harness and for clients that cannot.
            raise UpstreamUnavailable(
                "No server-side ASR is configured. Set VOSK_MODEL_DIR for offline recognition, "
                "or post a client transcript (the kiosk does this by default)."
            )

        from vosk import KaldiRecognizer  # type: ignore[import-not-found]

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as handle:
            handle.write(audio)
            handle.flush()
            with wave.open(handle.name, "rb") as wav:
                recogniser = KaldiRecognizer(model, wav.getframerate())
                recogniser.SetWords(True)
                while chunk := wav.readframes(4000):
                    recogniser.AcceptWaveform(chunk)
                result = json.loads(recogniser.FinalResult())
                duration_ms = int(1000 * wav.getnframes() / wav.getframerate())

        words = result.get("result", [])
        confidences = [(w["word"], float(w.get("conf", 0.0))) for w in words]
        mean = sum(c for _, c in confidences) / len(confidences) if confidences else 0.0
        text = result.get("text", "").strip()
        return Transcript(
            text=text,
            confidence=mean,
            language=language,
            backend=self.name,
            duration_ms=duration_ms,
            word_confidences=tuple(confidences),
            empty=not text,
        )

    # -------------------------------------------------------------- TTS

    def synthesise(self, text: str, *, language: str) -> Utterance:
        if shutil.which("say"):
            audio = self._say(text, language)
            if audio is not None:
                return Utterance(
                    audio=audio,
                    media_type="audio/wav",
                    text=text,
                    language=language,
                    backend=f"{self.name}:say",
                )
        if shutil.which("espeak-ng"):
            audio = self._espeak(text, language)
            if audio is not None:
                return Utterance(
                    audio=audio,
                    media_type="audio/wav",
                    text=text,
                    language=language,
                    backend=f"{self.name}:espeak-ng",
                )
        # No server-side voice. The kiosk falls back to the browser's speechSynthesis, which
        # every target device has. Returning empty audio with the flag set is honest about
        # what happened; returning silence without the flag would not be.
        return Utterance(
            audio=b"",
            media_type="audio/wav",
            text=text,
            language=language,
            backend=f"{self.name}:client",
            client_fallback=True,
        )

    def _say(self, text: str, language: str) -> bytes | None:
        """Try the language voice, then the system default. A missing Hindi voice on the demo
        laptop must degrade to *some* audio, not to silence — a non-literate patient who hears
        nothing has no way to use the kiosk at all."""
        voice = _MAC_VOICES.get(language)
        attempts = ([voice] if voice else []) + [None]
        for chosen in attempts:
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "speech.wav"
                cmd = ["say", "-o", str(out), "--data-format=LEI16@22050"]
                if chosen:
                    cmd += ["-v", chosen]
                cmd.append(text)
                try:
                    subprocess.run(cmd, check=True, capture_output=True, timeout=20)
                    return out.read_bytes()
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
                    continue
        log.warning("speech.say_unavailable", language=language)
        return None

    def _espeak(self, text: str, language: str) -> bytes | None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "speech.wav"
            try:
                subprocess.run(
                    ["espeak-ng", "-v", language, "-w", str(out), text],
                    check=True,
                    capture_output=True,
                    timeout=20,
                )
                return out.read_bytes()
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
                log.warning("speech.espeak_failed", error=str(exc)[:160])
                return None
