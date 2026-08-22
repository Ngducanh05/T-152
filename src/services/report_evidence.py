"""Backend-controlled Supabase Storage access for report evidence."""

from dataclasses import dataclass
from uuid import uuid4

import httpx
from fastapi import HTTPException, status

from src.core.config import Settings

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


@dataclass(frozen=True, slots=True)
class StoredReportEvidence:
    storage_path: str
    content_type: str
    size_bytes: int
    storage_mode: str = "real"


def _storage_error(code: str, message: str, status_code: int = 422) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def validate_report_image(
    *,
    content_type: str | None,
    size_bytes: int,
    max_bytes: int,
) -> str:
    normalized_type = (content_type or "").split(";")[0].strip().lower()
    if normalized_type not in ALLOWED_IMAGE_TYPES:
        raise _storage_error("REPORT_EVIDENCE_INVALID", "Report evidence must be an image.")
    if size_bytes <= 0 or size_bytes > max_bytes:
        raise _storage_error(
            "REPORT_EVIDENCE_INVALID",
            f"Report evidence must be between 1 byte and {max_bytes} bytes.",
        )
    return normalized_type


class ReportEvidenceStorage:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _configured(self) -> bool:
        return bool(
            self.settings.supabase_url
            and self.settings.supabase_service_role_key
            and self.settings.supabase_report_evidence_bucket
        )

    def _require_configured(self, *, allow_demo_fallback: bool) -> bool:
        if self._configured():
            return True
        if self.settings.demo_mode and allow_demo_fallback:
            return False
        raise _storage_error(
            "REPORT_EVIDENCE_STORAGE_UNCONFIGURED",
            "Report evidence storage is not configured.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    async def upload(
        self,
        *,
        report_id: str,
        data: bytes,
        content_type: str,
        allow_demo_fallback: bool = False,
    ) -> StoredReportEvidence:
        content_type = validate_report_image(
            content_type=content_type,
            size_bytes=len(data),
            max_bytes=self.settings.report_evidence_max_bytes,
        )
        extension = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            "image/heic": "heic",
            "image/heif": "heif",
        }[content_type]
        storage_path = f"reports/{report_id}/{uuid4()}.{extension}"

        if not self._require_configured(allow_demo_fallback=allow_demo_fallback):
            return StoredReportEvidence(
                storage_path,
                content_type,
                len(data),
                storage_mode="demo-synthetic",
            )

        base_url = self.settings.supabase_url.rstrip("/")
        service_key = self.settings.supabase_service_role_key
        assert service_key is not None
        headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": content_type,
            "x-upsert": "false",
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    (
                        f"{base_url}/storage/v1/object/"
                        f"{self.settings.supabase_report_evidence_bucket}/{storage_path}"
                    ),
                    headers=headers,
                    content=data,
                )
        except httpx.HTTPError as error:
            raise _storage_error(
                "REPORT_EVIDENCE_INVALID",
                "Report evidence storage is unavailable.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from error
        if response.status_code not in {status.HTTP_200_OK, status.HTTP_201_CREATED}:
            raise _storage_error(
                "REPORT_EVIDENCE_INVALID",
                "Report evidence could not be stored.",
                status.HTTP_502_BAD_GATEWAY,
            )
        return StoredReportEvidence(storage_path, content_type, len(data))

    async def create_signed_url(self, storage_path: str, *, expires_in: int = 300) -> str:
        if not self._require_configured(allow_demo_fallback=True):
            return f"demo-private://{storage_path}"

        base_url = self.settings.supabase_url.rstrip("/")
        service_key = self.settings.supabase_service_role_key
        assert service_key is not None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    (
                        f"{base_url}/storage/v1/object/sign/"
                        f"{self.settings.supabase_report_evidence_bucket}/{storage_path}"
                    ),
                    headers={
                        "apikey": service_key,
                        "Authorization": f"Bearer {service_key}",
                    },
                    json={"expiresIn": expires_in},
                )
        except httpx.HTTPError as error:
            raise _storage_error(
                "REPORT_EVIDENCE_INVALID",
                "Report evidence is temporarily unavailable.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from error
        if response.status_code != status.HTTP_200_OK:
            raise _storage_error(
                "REPORT_EVIDENCE_INVALID",
                "Report evidence is temporarily unavailable.",
                status.HTTP_502_BAD_GATEWAY,
            )
        payload = response.json()
        signed_url = payload.get("signedURL") or payload.get("signedUrl")
        if not isinstance(signed_url, str) or not signed_url:
            raise _storage_error(
                "REPORT_EVIDENCE_INVALID",
                "Report evidence is temporarily unavailable.",
                status.HTTP_502_BAD_GATEWAY,
            )
        if signed_url.startswith("http"):
            return signed_url
        return f"{base_url}/storage/v1{signed_url}"

    async def delete(self, storage_path: str | None) -> bool:
        if not storage_path:
            return True
        if not self._configured():
            return self.settings.demo_mode

        base_url = self.settings.supabase_url.rstrip("/")
        service_key = self.settings.supabase_service_role_key
        assert service_key is not None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.delete(
                    f"{base_url}/storage/v1/object/{self.settings.supabase_report_evidence_bucket}",
                    headers={
                        "apikey": service_key,
                        "Authorization": f"Bearer {service_key}",
                    },
                    json={"prefixes": [storage_path]},
                )
        except httpx.HTTPError:
            return False
        return status.HTTP_200_OK <= response.status_code < status.HTTP_300_MULTIPLE_CHOICES
