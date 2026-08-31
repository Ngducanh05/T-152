"""Compatibility adapter for wrong-parking evidence on shared image storage."""

from src.core.config import Settings
from src.services.image_evidence import (
    ALLOWED_IMAGE_TYPES,
    ImageEvidenceStorage,
    StoredImageEvidence,
    validate_image,
)

StoredReportEvidence = StoredImageEvidence


def validate_report_image(*, content_type: str | None, data: bytes, max_bytes: int) -> str:
    return validate_image(
        content_type=content_type,
        data=data,
        max_bytes=max_bytes,
        invalid_code="REPORT_EVIDENCE_INVALID",
        too_large_code="REPORT_EVIDENCE_TOO_LARGE",
        label="Report evidence",
    )


class ReportEvidenceStorage:
    def __init__(self, settings: Settings) -> None:
        self._storage = ImageEvidenceStorage(
            settings,
            namespace="reports",
            invalid_code="REPORT_EVIDENCE_INVALID",
            too_large_code="REPORT_EVIDENCE_TOO_LARGE",
            label="Report evidence",
            unconfigured_code="REPORT_EVIDENCE_STORAGE_UNCONFIGURED",
        )

    async def upload(
        self,
        *,
        report_id: str,
        data: bytes,
        content_type: str,
        allow_demo_fallback: bool = False,
    ) -> StoredReportEvidence:
        return await self._storage.upload(
            object_id=report_id,
            data=data,
            content_type=content_type,
            allow_demo_fallback=allow_demo_fallback,
        )

    async def create_signed_url(self, storage_path: str, *, expires_in: int = 300) -> str:
        return await self._storage.create_signed_url(storage_path, expires_in=expires_in)

    async def delete(self, storage_path: str | None) -> bool:
        return await self._storage.delete(storage_path)


__all__ = ["ALLOWED_IMAGE_TYPES", "ReportEvidenceStorage", "StoredReportEvidence", "validate_report_image"]
