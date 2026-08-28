from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from starlette.requests import Request

from src.api.main import create_app
from src.core.config import Settings
from src.core.observability import (
    ObservabilityRuntime,
    bind_observability_runtime,
    reset_observability_runtime,
)
from src.services.speech import SpeechTranscriptionError, transcribe_audio


@pytest.fixture
def speech_app():
    return create_app(
        Settings(
            _env_file=None,
            llm_api_key="test-key",
            speech_max_audio_bytes=8,
        )
    )


@pytest.mark.asyncio
async def test_speech_span_excludes_audio_key_and_transcript(monkeypatch: pytest.MonkeyPatch) -> None:
    exporter = InMemorySpanExporter()
    monkeypatch.setattr("src.core.observability.OTLPSpanExporter", lambda **_kwargs: exporter)

    class FakeResponse:
        status_code = 200

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict[str, str]:
            return {"text": "PRIVATE-TRANSCRIPT"}

    class FakeAsyncClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, *_args: object, **_kwargs: object) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr("src.services.speech.httpx.AsyncClient", FakeAsyncClient)
    settings = Settings(_env_file=None, llm_api_key="PRIVATE-API-KEY", speech_transcription_model="safe-model")
    runtime = ObservabilityRuntime(
        Settings(
            _env_file=None,
            observability_enabled=True,
            otel_exporter_otlp_endpoint="https://tenant.example/otlp",
            otel_exporter_otlp_headers="Authorization=Basic%20redacted",
        )
    )
    audio = b"PRIVATE-AUDIO-BYTES"
    binding = bind_observability_runtime(runtime)
    try:
        assert await transcribe_audio(audio, media_type="audio/webm", settings=settings) == "PRIVATE-TRANSCRIPT"
    finally:
        reset_observability_runtime(binding)
        runtime.shutdown()

    span = next(span for span in exporter.get_finished_spans() if span.name == "external.openai.speech.transcribe")
    assert span.attributes["gen_ai.request.model"] == "safe-model"
    assert span.attributes["audio.media_type"] == "audio/webm"
    rendered = str((span.attributes, span.events))
    for private_value in ("PRIVATE-API-KEY", "PRIVATE-AUDIO-BYTES", "PRIVATE-TRANSCRIPT"):
        assert private_value not in rendered


async def test_transcribes_supported_audio_without_persisting_it(speech_app):
    transcribe = AsyncMock(return_value="  tìm ô trống khu D  ")
    with patch("src.api.routes.speech.transcribe_audio", transcribe):
        async with speech_app.router.lifespan_context(speech_app):
            async with AsyncClient(
                transport=ASGITransport(app=speech_app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/api/v1/speech/transcriptions",
                    content=b"voice",
                    headers={"Content-Type": "audio/webm;codecs=opus"},
                )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {"text": "tìm ô trống khu D"},
        "message": None,
    }
    transcribe.assert_awaited_once()
    assert transcribe.await_args.kwargs["media_type"] == "audio/webm"


async def test_disabled_speech_returns_503_without_reading_or_transcribing_audio():
    application = create_app(Settings(_env_file=None, speech_enabled=False, llm_api_key=None))
    transcribe = AsyncMock()
    read_body = AsyncMock(return_value=b"voice")
    with (
        patch("src.api.routes.speech.transcribe_audio", transcribe),
        patch.object(Request, "body", read_body),
    ):
        async with application.router.lifespan_context(application):
            async with AsyncClient(
                transport=ASGITransport(app=application),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/api/v1/speech/transcriptions",
                    content=b"voice",
                    headers={"Content-Type": "audio/webm"},
                )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SPEECH_DISABLED"
    read_body.assert_not_awaited()
    transcribe.assert_not_awaited()


async def test_rejects_empty_or_unsupported_audio(speech_app):
    async with speech_app.router.lifespan_context(speech_app):
        async with AsyncClient(
            transport=ASGITransport(app=speech_app),
            base_url="http://test",
        ) as client:
            empty = await client.post(
                "/api/v1/speech/transcriptions",
                content=b"",
                headers={"Content-Type": "audio/webm"},
            )
            unsupported = await client.post(
                "/api/v1/speech/transcriptions",
                content=b"voice",
                headers={"Content-Type": "text/plain"},
            )

    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "SPEECH_AUDIO_INVALID"
    assert unsupported.status_code == 400
    assert unsupported.json()["error"]["code"] == "SPEECH_AUDIO_INVALID"


async def test_rejects_audio_over_the_cost_guard_size_limit(speech_app):
    async with speech_app.router.lifespan_context(speech_app):
        async with AsyncClient(
            transport=ASGITransport(app=speech_app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/speech/transcriptions",
                content=b"123456789",
                headers={"Content-Type": "audio/webm"},
            )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "SPEECH_AUDIO_TOO_LARGE"


async def test_returns_safe_error_when_provider_fails(speech_app):
    transcribe = AsyncMock(side_effect=SpeechTranscriptionError("secret provider response"))
    with patch("src.api.routes.speech.transcribe_audio", transcribe):
        async with speech_app.router.lifespan_context(speech_app):
            async with AsyncClient(
                transport=ASGITransport(app=speech_app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/api/v1/speech/transcriptions",
                    content=b"voice",
                    headers={"Content-Type": "audio/webm"},
                )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SPEECH_TRANSCRIPTION_UNAVAILABLE"
    assert "secret" not in response.text


@pytest.mark.parametrize(
    ("reason", "status_code", "error_code"),
    [
        ("invalid_audio", 400, "SPEECH_AUDIO_INVALID"),
        ("no_transcript", 422, "SPEECH_NO_TRANSCRIPT"),
        ("timeout", 504, "SPEECH_TRANSCRIPTION_TIMEOUT"),
    ],
)
async def test_returns_actionable_transcription_errors(speech_app, reason, status_code, error_code):
    transcribe = AsyncMock(side_effect=SpeechTranscriptionError(reason))
    with patch("src.api.routes.speech.transcribe_audio", transcribe):
        async with speech_app.router.lifespan_context(speech_app):
            async with AsyncClient(
                transport=ASGITransport(app=speech_app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/api/v1/speech/transcriptions",
                    content=b"voice",
                    headers={"Content-Type": "audio/webm"},
                )

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == error_code
