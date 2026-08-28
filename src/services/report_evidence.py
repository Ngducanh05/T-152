"""Backend-controlled Supabase Storage access for report evidence."""

from contextlib import nullcontext
from dataclasses import dataclass
from uuid import uuid4

import httpx
from fastapi import HTTPException, status
from opentelemetry.trace import SpanKind

from src.core.config import Settings
from src.core.observability import get_active_observability

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
    data: bytes,
    max_bytes: int,
) -> str:
    normalized_type = (content_type or "").split(";")[0].strip().lower()
    if normalized_type not in ALLOWED_IMAGE_TYPES:
        raise _storage_error(
            "REPORT_EVIDENCE_INVALID",
            "Report evidence must be a supported image.",
            status.HTTP_400_BAD_REQUEST,
        )
    if len(data) > max_bytes:
        raise _storage_error(
            "REPORT_EVIDENCE_TOO_LARGE",
            f"Report evidence must not exceed {max_bytes} bytes.",
            status.HTTP_413_CONTENT_TOO_LARGE,
        )
    if not data or not _signature_matches(normalized_type, data):
        raise _storage_error(
            "REPORT_EVIDENCE_INVALID",
            "Report evidence content does not match its declared image type.",
            status.HTTP_400_BAD_REQUEST,
        )
    return normalized_type


def _signature_matches(content_type: str, data: bytes) -> bool:
    if content_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if content_type not in {"image/heic", "image/heif"} or len(data) < 16:
        return False

    box_size = int.from_bytes(data[:4], "big")
    if data[4:8] != b"ftyp" or box_size < 16 or box_size > len(data):
        return False
    brands = {data[8:12]}
    brands.update(data[offset : offset + 4] for offset in range(16, box_size, 4))
    expected_brands = (
        {b"heic", b"heix", b"hevc", b"hevx"} if content_type == "image/heic" else {b"mif1", b"msf1", b"heif"}
    )
    return bool(brands & expected_brands)


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

    @staticmethod
    def _operation_context(name: str, operation: str, method: str):
        runtime = get_active_observability()
        return runtime, (
            runtime.start_span(
                name,
                kind=SpanKind.CLIENT,
                attributes={
                    "external.system": "supabase",
                    "external.operation": operation,
                    "http.request.method": method,
                },
            )
            if runtime is not None
            else nullcontext(None)
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
            data=data,
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
        runtime, context_manager = self._operation_context(
            "external.supabase.storage.upload", "storage.upload", "POST"
        )
        provider_error: httpx.HTTPError | None = None
        with context_manager as span:
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    response = await client.post(
                        (f"{base_url}/storage/v1/object/{self.settings.supabase_report_evidence_bucket}/{storage_path}"),
                        headers=headers,
                        content=data,
                    )
            except httpx.HTTPError as error:
                provider_error = error
                if runtime is not None:
                    runtime.mark_span_failed(span, exception=error)
            else:
                if span is not None:
                    span.set_attribute("http.response.status_code", response.status_code)
                    span.set_attribute(
                        "outcome", "success" if response.status_code in {status.HTTP_200_OK, status.HTTP_201_CREATED} else "error"
                    )
                if response.status_code not in {status.HTTP_200_OK, status.HTTP_201_CREATED} and runtime is not None:
                    runtime.mark_span_failed(span, error_code="REPORT_EVIDENCE_INVALID")
        if provider_error is not None:
            raise _storage_error(
                "REPORT_EVIDENCE_INVALID",
                "Report evidence storage is unavailable.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from provider_error
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
        runtime, context_manager = self._operation_context(
            "external.supabase.storage.sign", "storage.sign", "POST"
        )
        provider_error: httpx.HTTPError | None = None
        with context_manager as span:
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
                provider_error = error
                if runtime is not None:
                    runtime.mark_span_failed(span, exception=error)
            else:
                if span is not None:
                    span.set_attribute("http.response.status_code", response.status_code)
                    span.set_attribute("outcome", "success" if response.status_code == status.HTTP_200_OK else "error")
                if response.status_code != status.HTTP_200_OK and runtime is not None:
                    runtime.mark_span_failed(span, error_code="REPORT_EVIDENCE_INVALID")
        if provider_error is not None:
            raise _storage_error(
                "REPORT_EVIDENCE_INVALID",
                "Report evidence is temporarily unavailable.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from provider_error
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
        runtime, context_manager = self._operation_context(
            "external.supabase.storage.delete", "storage.delete", "DELETE"
        )
        provider_error: httpx.HTTPError | None = None
        with context_manager as span:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.request(
                        "DELETE",
                        f"{base_url}/storage/v1/object/{self.settings.supabase_report_evidence_bucket}",
                        headers={
                            "apikey": service_key,
                            "Authorization": f"Bearer {service_key}",
                        },
                        json={"prefixes": [storage_path]},
                    )
            except httpx.HTTPError as error:
                provider_error = error
                if runtime is not None:
                    runtime.mark_span_failed(span, exception=error)
            else:
                success = status.HTTP_200_OK <= response.status_code < status.HTTP_300_MULTIPLE_CHOICES
                if span is not None:
                    span.set_attribute("http.response.status_code", response.status_code)
                    span.set_attribute("outcome", "success" if success else "error")
                if not success and runtime is not None:
                    runtime.mark_span_failed(span, error_code="REPORT_EVIDENCE_INVALID")
        if provider_error is not None:
            return False
        return status.HTTP_200_OK <= response.status_code < status.HTTP_300_MULTIPLE_CHOICES
