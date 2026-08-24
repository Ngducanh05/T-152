from io import BytesIO
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from src.api.routes.reports import _read_bounded_evidence
from src.core.config import Settings
from src.services.report_evidence import ReportEvidenceStorage, validate_report_image


@pytest.mark.asyncio
async def test_report_evidence_storage_fails_closed_when_not_configured() -> None:
    storage = ReportEvidenceStorage(
        Settings(
            demo_mode=False,
            supabase_url=None,
            supabase_service_role_key=None,
            supabase_report_evidence_bucket="",
        )
    )

    with pytest.raises(Exception) as exc_info:
        await storage.upload(
            report_id="REPORT-001",
            data=b"\xff\xd8\xffimage-bytes",
            content_type="image/jpeg",
        )

    error = exc_info.value
    assert getattr(error, "status_code", None) == 503
    assert getattr(error, "detail", {}).get("code") == "REPORT_EVIDENCE_STORAGE_UNCONFIGURED"


@pytest.mark.asyncio
async def test_report_evidence_delete_surfaces_failed_storage_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_methods: list[str] = []

    class FakeResponse:
        status_code = 500

    class FakeAsyncClient:
        def __init__(self, **_kwargs: object) -> None:
            return None

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def request(
            self,
            method: str,
            *_args: object,
            **_kwargs: object,
        ) -> FakeResponse:
            request_methods.append(method)
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    storage = ReportEvidenceStorage(
        Settings(
            demo_mode=False,
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-role",
            supabase_report_evidence_bucket="reports",
        )
    )

    assert await storage.delete("reports/REPORT-001/evidence.jpg") is False
    assert request_methods == ["DELETE"]


@pytest.mark.asyncio
async def test_report_evidence_delete_fails_closed_when_unconfigured_outside_demo() -> None:
    storage = ReportEvidenceStorage(
        Settings(
            demo_mode=False,
            supabase_url=None,
            supabase_service_role_key=None,
            supabase_report_evidence_bucket="",
        )
    )

    assert await storage.delete("reports/REPORT-001/evidence.jpg") is False


@pytest.mark.asyncio
async def test_report_evidence_delete_accepts_synthetic_demo_path_when_unconfigured() -> None:
    storage = ReportEvidenceStorage(
        Settings(
            demo_mode=True,
            supabase_url=None,
            supabase_service_role_key=None,
            supabase_report_evidence_bucket="",
        )
    )

    assert await storage.delete("reports/REPORT-001/evidence.jpg") is True


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
def test_report_evidence_accepts_matching_image_signatures(
    content_type: str,
    data: bytes,
) -> None:
    assert validate_report_image(
        content_type=content_type,
        data=data,
        max_bytes=5_000_000,
    ) == content_type


@pytest.mark.parametrize(
    ("content_type", "data"),
    [
        ("image/jpeg", b"not-a-jpeg"),
        ("image/png", b"\xff\xd8\xffspoofed"),
        ("image/gif", b"GIF89a"),
        ("image/webp", b""),
    ],
)
def test_report_evidence_rejects_mime_spoofing_and_invalid_signatures(
    content_type: str,
    data: bytes,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_report_image(
            content_type=content_type,
            data=data,
            max_bytes=5_000_000,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "REPORT_EVIDENCE_INVALID"


@pytest.mark.asyncio
async def test_upload_file_size_rejects_before_read() -> None:
    evidence = UploadFile(
        BytesIO(b"small"),
        filename="declared-large.jpg",
        size=5_000_001,
        headers=Headers({"content-type": "image/jpeg"}),
    )
    evidence.read = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(HTTPException) as exc_info:
        await _read_bounded_evidence(evidence, 5_000_000)

    assert exc_info.value.status_code == 413
    assert exc_info.value.detail["code"] == "REPORT_EVIDENCE_TOO_LARGE"
    evidence.read.assert_not_awaited()  # type: ignore[attr-defined]
    await evidence.close()


@pytest.mark.asyncio
async def test_stream_read_stops_within_one_chunk_after_limit() -> None:
    stream = BytesIO(b"\xff\xd8\xff" + b"x" * 5_100_000)
    evidence = UploadFile(
        stream,
        filename="streamed-large.jpg",
        size=None,
        headers=Headers({"content-type": "image/jpeg"}),
    )

    with pytest.raises(HTTPException) as exc_info:
        await _read_bounded_evidence(evidence, 5_000_000)

    assert exc_info.value.status_code == 413
    assert exc_info.value.detail["code"] == "REPORT_EVIDENCE_TOO_LARGE"
    assert stream.tell() <= 5_000_000 + 64 * 1024
    await evidence.close()
