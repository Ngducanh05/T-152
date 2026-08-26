from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.dependencies import require_authenticated_or_demo
from src.core.config import Settings
from src.models.common import ErrorResponse, SuccessResponse
from src.models.schemas import ErrorCode, SpeechTranscriptionResponse
from src.services.speech import SpeechTranscriptionError, transcribe_audio

router = APIRouter(
    prefix="/speech",
    tags=["Speech"],
    dependencies=[Depends(require_authenticated_or_demo)],
)
logger = logging.getLogger(__name__)

_ALLOWED_MEDIA_TYPES = frozenset({"audio/mp4", "audio/mpeg", "audio/ogg", "audio/wav", "audio/webm"})


def _speech_error(status_code: int, code: ErrorCode, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code.value, "message": message},
    )


@router.post(
    "/transcriptions",
    response_model=SuccessResponse[SpeechTranscriptionResponse],
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
)
async def create_transcription(
    request: Request,
) -> SuccessResponse[SpeechTranscriptionResponse]:
    settings: Settings = request.app.state.settings
    if not settings.speech_enabled:
        raise _speech_error(
            503,
            ErrorCode.SPEECH_DISABLED,
            "Speech transcription is currently disabled.",
        )

    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in _ALLOWED_MEDIA_TYPES:
        raise _speech_error(
            400,
            ErrorCode.SPEECH_AUDIO_INVALID,
            "Audio must be webm, ogg, mp4, mpeg, or wav.",
        )

    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit():
        if int(content_length) > settings.speech_max_audio_bytes:
            raise _speech_error(
                413,
                ErrorCode.SPEECH_AUDIO_TOO_LARGE,
                "Audio exceeds the configured size limit.",
            )

    audio = await request.body()
    if not audio:
        raise _speech_error(
            400,
            ErrorCode.SPEECH_AUDIO_INVALID,
            "Audio must not be empty.",
        )
    if len(audio) > settings.speech_max_audio_bytes:
        raise _speech_error(
            413,
            ErrorCode.SPEECH_AUDIO_TOO_LARGE,
            "Audio exceeds the configured size limit.",
        )

    try:
        text = (await transcribe_audio(audio, media_type=media_type, settings=settings)).strip()
    except SpeechTranscriptionError as error:
        logger.warning(
            "speech_transcription_failed request_id=%s reason=%s",
            getattr(request.state, "request_id", "unknown"),
            error.reason,
        )
        if error.reason == "invalid_audio":
            raise _speech_error(
                400,
                ErrorCode.SPEECH_AUDIO_INVALID,
                "The recorded audio could not be decoded.",
            ) from error
        if error.reason == "no_transcript":
            raise _speech_error(
                422,
                ErrorCode.SPEECH_NO_TRANSCRIPT,
                "No speech was detected in the recording.",
            ) from error
        if error.reason == "timeout":
            raise _speech_error(
                504,
                ErrorCode.SPEECH_TRANSCRIPTION_TIMEOUT,
                "Speech transcription timed out.",
            ) from error
        raise _speech_error(
            503,
            ErrorCode.SPEECH_TRANSCRIPTION_UNAVAILABLE,
            "Speech transcription is temporarily unavailable.",
        ) from error

    return SuccessResponse(data=SpeechTranscriptionResponse(text=text))


__all__ = ["router"]
