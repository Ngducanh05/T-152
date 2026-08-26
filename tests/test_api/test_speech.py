from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from src.api.main import create_app
from src.core.config import Settings
from src.services.speech import SpeechTranscriptionError


@pytest.fixture
def speech_app():
    return create_app(
        Settings(
            _env_file=None,
            llm_api_key="test-key",
            speech_max_audio_bytes=8,
        )
    )


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
