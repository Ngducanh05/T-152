from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from src.core.config import Settings
from src.services.image_evidence import ImageEvidenceStorage, read_bounded_image, validate_image


@pytest.mark.parametrize(
    ("content_type", "data"),
    [
        ("image/jpeg", b"\xff\xd8\xffjpeg"),
        ("image/png", b"\x89PNG\r\n\x1a\npng"),
        ("image/webp", b"RIFF\x04\x00\x00\x00WEBPdata"),
        ("image/heic", b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic"),
        ("image/heif", b"\x00\x00\x00\x18ftypmif1\x00\x00\x00\x00heifmif1"),
    ],
)
def test_observation_evidence_accepts_supported_matching_signatures(
    content_type: str,
    data: bytes,
) -> None:
    assert validate_image(
        content_type=content_type,
        data=data,
        max_bytes=5_000_000,
        invalid_code="OBSERVATION_EVIDENCE_INVALID",
        too_large_code="OBSERVATION_EVIDENCE_TOO_LARGE",
        label="Observation evidence",
    ) == content_type


@pytest.mark.parametrize(
    ("content_type", "data", "max_bytes", "status_code", "code"),
    [
        ("image/jpeg", b"not-a-jpeg", 5_000_000, 400, "OBSERVATION_EVIDENCE_INVALID"),
        ("image/png", b"\xff\xd8\xffspoofed", 5_000_000, 400, "OBSERVATION_EVIDENCE_INVALID"),
        ("image/gif", b"GIF89a", 5_000_000, 400, "OBSERVATION_EVIDENCE_INVALID"),
        ("image/webp", b"", 5_000_000, 400, "OBSERVATION_EVIDENCE_INVALID"),
        ("image/jpeg", b"\xff\xd8\xffoversized", 3, 413, "OBSERVATION_EVIDENCE_TOO_LARGE"),
    ],
)
def test_observation_evidence_rejects_invalid_or_oversized_bytes(
    content_type: str,
    data: bytes,
    max_bytes: int,
    status_code: int,
    code: str,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_image(
            content_type=content_type,
            data=data,
            max_bytes=max_bytes,
            invalid_code="OBSERVATION_EVIDENCE_INVALID",
            too_large_code="OBSERVATION_EVIDENCE_TOO_LARGE",
            label="Observation evidence",
        )

    assert exc_info.value.status_code == status_code
    assert exc_info.value.detail["code"] == code


@pytest.mark.asyncio
async def test_observation_evidence_read_rejects_declared_oversize_before_read() -> None:
    evidence = UploadFile(
        BytesIO(b"small"),
        filename="declared-large.jpg",
        size=5_000_001,
        headers=Headers({"content-type": "image/jpeg"}),
    )
    evidence.read = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(HTTPException) as exc_info:
        await read_bounded_image(
            evidence,
            max_bytes=5_000_000,
            too_large_code="OBSERVATION_EVIDENCE_TOO_LARGE",
            label="Observation evidence",
        )

    assert exc_info.value.status_code == 413
    assert exc_info.value.detail["code"] == "OBSERVATION_EVIDENCE_TOO_LARGE"
    evidence.read.assert_not_awaited()  # type: ignore[attr-defined]
    await evidence.close()


@pytest.mark.asyncio
async def test_observation_evidence_storage_uses_private_namespace_and_fails_closed() -> None:
    demo_storage = ImageEvidenceStorage(
        Settings(
            demo_mode=True,
            supabase_url=None,
            supabase_service_role_key=None,
            supabase_report_evidence_bucket="",
        ),
        namespace="slot-observations",
        invalid_code="OBSERVATION_EVIDENCE_INVALID",
        too_large_code="OBSERVATION_EVIDENCE_TOO_LARGE",
        label="Observation evidence",
    )
    synthetic = await demo_storage.upload(
        object_id="OBSERVATION-001",
        data=b"\xff\xd8\xffjpeg",
        content_type="image/jpeg",
        allow_demo_fallback=True,
    )
    assert synthetic.storage_path.startswith("slot-observations/OBSERVATION-001/")
    assert synthetic.storage_mode == "demo-synthetic"

    storage = ImageEvidenceStorage(
        Settings(
            demo_mode=False,
            supabase_url=None,
            supabase_service_role_key=None,
            supabase_report_evidence_bucket="",
        ),
        namespace="slot-observations",
        invalid_code="OBSERVATION_EVIDENCE_INVALID",
        too_large_code="OBSERVATION_EVIDENCE_TOO_LARGE",
        label="Observation evidence",
    )

    with pytest.raises(HTTPException) as exc_info:
        await storage.upload(
            object_id="OBSERVATION-001",
            data=b"\xff\xd8\xffjpeg",
            content_type="image/jpeg",
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "OBSERVATION_EVIDENCE_INVALID"
