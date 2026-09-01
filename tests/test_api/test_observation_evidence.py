"""Focused contracts for optional adjacent-observation evidence."""

from io import BytesIO

import pytest
from fastapi import HTTPException

from src.api.main import create_app
from src.core.config import get_settings
from src.services.report_evidence import (
    ObservationEvidenceStorage,
    validate_observation_image,
)

JPEG = b"\xff\xd8\xff" + b"jpeg-data"
PNG = b"\x89PNG\r\n\x1a\n" + b"png-data"
WEBP = b"RIFF" + (4).to_bytes(4, "little") + b"WEBP" + b"data"
HEIC = (20).to_bytes(4, "big") + b"ftyp" + b"heic" + b"\x00\x00\x00\x00" + b"heic"
HEIF = (20).to_bytes(4, "big") + b"ftyp" + b"mif1" + b"\x00\x00\x00\x00" + b"heif"


@pytest.mark.parametrize(
    ("content_type", "data"),
    [
        ("image/jpeg", JPEG),
        ("image/png", PNG),
        ("image/webp", WEBP),
        ("image/heic", HEIC),
        ("image/heif", HEIF),
    ],
)
def test_observation_evidence_accepts_supported_real_signatures(
    content_type: str,
    data: bytes,
):
    assert (
        validate_observation_image(
            content_type=content_type,
            data=data,
            max_bytes=5_000_000,
        )
        == content_type
    )


@pytest.mark.parametrize(
    ("content_type", "data", "expected_code"),
    [
        ("image/jpeg", b"", "OBSERVATION_EVIDENCE_INVALID"),
        ("image/gif", b"GIF89a", "OBSERVATION_EVIDENCE_INVALID"),
        ("image/png", JPEG, "OBSERVATION_EVIDENCE_INVALID"),
        ("image/jpeg", JPEG + b"x" * 20, "OBSERVATION_EVIDENCE_TOO_LARGE"),
    ],
)
def test_observation_evidence_rejects_invalid_or_oversized_content(
    content_type: str,
    data: bytes,
    expected_code: str,
):
    max_bytes = 10 if expected_code == "OBSERVATION_EVIDENCE_TOO_LARGE" else 5_000_000
    with pytest.raises(HTTPException) as caught:
        validate_observation_image(
            content_type=content_type,
            data=data,
            max_bytes=max_bytes,
        )
    assert caught.value.detail["code"] == expected_code


@pytest.mark.asyncio
async def test_observation_storage_reuses_private_bucket_and_prefix_without_public_url():
    settings = get_settings().model_copy(
        update={
            "demo_mode": True,
            "supabase_url": None,
            "supabase_service_role_key": None,
            "supabase_report_evidence_bucket": None,
        }
    )
    stored = await ObservationEvidenceStorage(settings).upload(
        observation_id="OBSERVATION-001",
        data=JPEG,
        content_type="image/jpeg",
        allow_demo_fallback=True,
    )

    assert stored.storage_path.startswith("slot-observations/OBSERVATION-001/")
    assert stored.storage_path.endswith(".jpg")
    assert stored.content_type == "image/jpeg"
    assert stored.size_bytes == len(JPEG)
    assert not hasattr(stored, "public_url")
    assert not isinstance(stored, BytesIO)


def test_observation_openapi_documents_json_and_optional_multipart_contracts():
    operation = create_app().openapi()["paths"][
        "/api/v1/parking/slots/{slot_id}/observation"
    ]["post"]
    content = operation["requestBody"]["content"]

    assert set(content) == {"application/json", "multipart/form-data"}
    multipart = content["multipart/form-data"]["schema"]
    assert multipart["required"] == [
        "user_id",
        "observed_status",
        "expected_slot_version",
    ]
    assert multipart["properties"]["evidence"] == {
        "type": "string",
        "format": "binary",
    }


def test_admin_observation_evidence_openapi_documents_storage_failures():
    operation = create_app().openapi()["paths"][
        "/api/v1/admin/slot-observations/{observation_id}/evidence-url"
    ]["get"]
    responses = operation["responses"]

    assert {"200", "404", "422", "502", "503"} <= responses.keys()


def _unconfigured_observation_settings():
    return get_settings().model_copy(
        update={
            "demo_mode": False,
            "supabase_url": None,
            "supabase_service_role_key": None,
        }
    )


def _assert_observation_storage_error(error: HTTPException) -> None:
    assert error.status_code == 503
    assert error.detail["code"] == "OBSERVATION_EVIDENCE_INVALID"
    assert "REPORT_EVIDENCE" not in error.detail["code"]
    assert "Report evidence" not in error.detail["message"]


@pytest.mark.asyncio
async def test_observation_upload_configuration_error_uses_observation_namespace():
    with pytest.raises(HTTPException) as caught:
        await ObservationEvidenceStorage(_unconfigured_observation_settings()).upload(
            observation_id="OBSERVATION-ERROR",
            data=JPEG,
            content_type="image/jpeg",
            allow_demo_fallback=False,
        )

    _assert_observation_storage_error(caught.value)


@pytest.mark.asyncio
async def test_observation_signed_url_configuration_error_uses_observation_namespace():
    with pytest.raises(HTTPException) as caught:
        await ObservationEvidenceStorage(
            _unconfigured_observation_settings()
        ).create_signed_url("slot-observations/OBSERVATION-ERROR/evidence.jpg")

    _assert_observation_storage_error(caught.value)
