from __future__ import annotations

import asyncio
from contextlib import nullcontext

import httpx
from opentelemetry.trace import SpanKind

from src.core.config import Settings
from src.core.observability import get_active_observability


class SpeechTranscriptionError(RuntimeError):
    """Raised when transcription cannot safely produce public text."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def transcribe_audio(
    audio: bytes,
    *,
    media_type: str,
    settings: Settings,
) -> str:
    api_key = (settings.llm_api_key or "").strip()
    if not api_key:
        raise SpeechTranscriptionError("configuration")

    extension = {
        "audio/mp4": "m4a",
        "audio/mpeg": "mp3",
        "audio/ogg": "ogg",
        "audio/wav": "wav",
        "audio/webm": "webm",
    }.get(media_type, "webm")

    payload: object | None = None
    runtime = get_active_observability()
    context_manager = (
        runtime.start_span(
            "external.openai.speech.transcribe",
            kind=SpanKind.CLIENT,
            attributes={
                "external.system": "openai",
                "external.operation": "speech.transcribe",
                "gen_ai.request.model": settings.speech_transcription_model,
                "audio.media_type": media_type,
                "retry.count": 0,
            },
        )
        if runtime is not None
        else nullcontext(None)
    )
    with context_manager as span:
        async with httpx.AsyncClient(timeout=settings.speech_timeout_seconds) as client:
            for attempt in range(settings.speech_max_retries + 1):
                if span is not None:
                    span.set_attribute("retry.count", attempt)
                try:
                    response = await client.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        data={
                            "model": settings.speech_transcription_model,
                            "language": "vi",
                            "response_format": "json",
                        },
                        files={"file": (f"voice.{extension}", audio, media_type)},
                    )
                    if span is not None:
                        span.set_attribute("http.response.status_code", response.status_code)
                    if response.status_code == 400:
                        raise SpeechTranscriptionError("invalid_audio")
                    if response.status_code in {401, 403}:
                        raise SpeechTranscriptionError("configuration")
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt < settings.speech_max_retries:
                            await asyncio.sleep(0.25 * (attempt + 1))
                            continue
                        raise SpeechTranscriptionError("provider")
                    response.raise_for_status()
                    payload = response.json()
                    if span is not None:
                        span.set_attribute("outcome", "success")
                    break
                except SpeechTranscriptionError:
                    raise
                except httpx.TimeoutException as error:
                    if attempt < settings.speech_max_retries:
                        await asyncio.sleep(0.25 * (attempt + 1))
                        continue
                    raise SpeechTranscriptionError("timeout") from error
                except (httpx.HTTPError, ValueError) as error:
                    if attempt < settings.speech_max_retries:
                        await asyncio.sleep(0.25 * (attempt + 1))
                        continue
                    raise SpeechTranscriptionError("provider") from error

    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise SpeechTranscriptionError("no_transcript")
    return text.strip()


__all__ = ["SpeechTranscriptionError", "transcribe_audio"]
