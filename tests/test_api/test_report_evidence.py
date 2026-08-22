import httpx
import pytest

from src.core.config import Settings
from src.services.report_evidence import ReportEvidenceStorage


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
            data=b"image-bytes",
            content_type="image/jpeg",
        )

    error = exc_info.value
    assert getattr(error, "status_code", None) == 503
    assert getattr(error, "detail", {}).get("code") == "REPORT_EVIDENCE_STORAGE_UNCONFIGURED"


@pytest.mark.asyncio
async def test_report_evidence_delete_surfaces_failed_storage_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        status_code = 500

    class FakeAsyncClient:
        def __init__(self, **_kwargs: object) -> None:
            return None

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def delete(self, *_args: object, **_kwargs: object) -> FakeResponse:
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
