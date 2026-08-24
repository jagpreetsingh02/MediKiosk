"""Bhashini / AI4Bharat backend, behind the same protocol.

Written against the Dhruva inference API. It is **not** on the critical path and the build was
never blocked on obtaining credentials: with no key configured it raises
:class:`UpstreamUnavailable` at construction and the registry selects the local backend
instead. Swapping to it in a deployment that has government credentials is one env var.

Left honestly unverified: this has been exercised against a recorded fixture, not against the
live Dhruva endpoint, because we have no credentials. The request/response shapes follow the
published pipeline contract. Treat the first live call as an integration test.
"""

from __future__ import annotations

import base64

import httpx

from app.core.config import settings
from app.core.errors import UpstreamUnavailable
from app.speech.protocol import Transcript, Utterance

ASR_TASK = "asr"
TTS_TASK = "tts"


class BhashiniSpeechBackend:
    """Satisfies `SpeechBackend`."""

    name = "bhashini"
    offline = False
    languages: tuple[str, ...] = (
        "en", "hi", "bn", "ta", "te", "mr", "kn", "ml", "gu", "pa", "or", "as",
    )

    def __init__(self) -> None:
        if not (settings.bhashini_api_key and settings.bhashini_pipeline_id):
            raise UpstreamUnavailable(
                "Bhashini credentials are not configured (BHASHINI_API_KEY, "
                "BHASHINI_PIPELINE_ID). The local backend is used instead."
            )
        self._headers = {
            "Authorization": settings.bhashini_api_key,
            "userID": settings.bhashini_user_id or "",
            "Content-Type": "application/json",
        }

    def _call(self, task: str, payload: dict) -> dict:
        try:
            response = httpx.post(
                settings.bhashini_base_url,
                json={
                    "pipelineTasks": [{"taskType": task, "config": payload["config"]}],
                    "inputData": payload["inputData"],
                },
                headers=self._headers,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable(f"Bhashini {task} call failed: {exc}") from exc

    def transcribe(self, audio: bytes, *, language: str, media_type: str) -> Transcript:
        body = self._call(
            ASR_TASK,
            {
                "config": {
                    "language": {"sourceLanguage": language},
                    "serviceId": settings.bhashini_pipeline_id,
                    "audioFormat": "wav",
                    "samplingRate": 16000,
                },
                "inputData": {"audio": [{"audioContent": base64.b64encode(audio).decode()}]},
            },
        )
        output = (body.get("pipelineResponse") or [{}])[0].get("output") or [{}]
        text = str(output[0].get("source", "")).strip()
        # Dhruva returns no confidence, so this reports none. Assigning one — even the
        # threshold itself, as an earlier version did — would claim a measurement that was
        # never made. The caller handles `unavailable` explicitly.
        return Transcript(
            text=text,
            confidence=None,
            language=language,
            backend=self.name,
            empty=not text,
        )

    def synthesise(self, text: str, *, language: str) -> Utterance:
        body = self._call(
            TTS_TASK,
            {
                "config": {
                    "language": {"sourceLanguage": language},
                    "serviceId": settings.bhashini_pipeline_id,
                    "gender": "female",
                },
                "inputData": {"input": [{"source": text}]},
            },
        )
        output = (body.get("pipelineResponse") or [{}])[0].get("audio") or [{}]
        encoded = output[0].get("audioContent", "")
        return Utterance(
            audio=base64.b64decode(encoded) if encoded else b"",
            media_type="audio/wav",
            text=text,
            language=language,
            backend=self.name,
            client_fallback=not encoded,
        )
