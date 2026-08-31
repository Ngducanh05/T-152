"""Shared validation and private Supabase Storage access for image evidence."""

from contextlib import nullcontext
from dataclasses import dataclass
from uuid import uuid4

import httpx
from fastapi import HTTPException, status
from opentelemetry.trace import SpanKind
from starlette.datastructures import UploadFile

from src.core.config import Settings
from src.core.observability import get_active_observability

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
EVIDENCE_CHUNK_BYTES = 64 * 1024
_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
    "image/heif": "heif",
}


@dataclass(frozen=True, slots=True)
class StoredImageEvidence:
    storage_path: str
    content_type: str
    size_bytes: int
    storage_mode: str = "real"


def image_http_error(code: str, message: str, status_code: int = 422) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def read_bounded_image(
    upload: UploadFile,
    *,
    max_bytes: int,
    too_large_code: str,
    label: str,
) -> bytes:
    """Read a multipart file in fixed chunks so a bogus upload cannot grow unbounded."""
    if upload.size is not None and upload.size > max_bytes:
        raise image_http_error(
            too_large_code,
            f"{label} must not exceed {max_bytes} bytes.",
            status.HTTP_413_CONTENT_TOO_LARGE,
        )
    content = bytearray()
    while True:
        chunk = await upload.read(EVIDENCE_CHUNK_BYTES)
        if not chunk:
            return bytes(content)
        content.extend(chunk)
        if len(content) > max_bytes:
            raise image_http_error(
                too_large_code,
                f"{label} must not exceed {max_bytes} bytes.",
                status.HTTP_413_CONTENT_TOO_LARGE,
            )


def validate_image(
    *,
    content_type: str | None,
    data: bytes,
    max_bytes: int,
    invalid_code: str,
    too_large_code: str,
    label: str,
) -> str:
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_type not in ALLOWED_IMAGE_TYPES:
        raise image_http_error(
            invalid_code,
            f"{label} must be a supported image.",
            status.HTTP_400_BAD_REQUEST,
        )
    if len(data) > max_bytes:
        raise image_http_error(
            too_large_code,
            f"{label} must not exceed {max_bytes} bytes.",
            status.HTTP_413_CONTENT_TOO_LARGE,
        )
    if not data or not signature_matches(normalized_type, data):
        raise image_http_error(
            invalid_code,
            f"{label} content does not match its declared image type.",
            status.HTTP_400_BAD_REQUEST,
        )
    return normalized_type


def signature_matches(content_type: str, data: bytes) -> bool:
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
    brands = {data[8:12], *(data[offset : offset + 4] for offset in range(16, box_size, 4))}
    expected = (
        {b"heic", b"heix", b"hevc", b"hevx"}
        if content_type == "image/heic"
        else {b"mif1", b"msf1", b"heif"}
    )
    return bool(brands & expected)


class ImageEvidenceStorage:
    """Backend-only private object storage parameterized by a safe namespace."""

    def __init__(
        self,
        settings: Settings,
        *,
        namespace: str,
        invalid_code: str,
        too_large_code: str,
        label: str,
        unconfigured_code: str | None = None,
    ) -> None:
        self.settings = settings
        self.namespace = namespace
        self.invalid_code = invalid_code
        self.too_large_code = too_large_code
        self.label = label
        self.unconfigured_code = unconfigured_code or invalid_code

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
        raise image_http_error(
            self.unconfigured_code,
            f"{self.label} storage is not configured.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    @staticmethod
    def _operation_context(name: str, operation: str, method: str):
        runtime = get_active_observability()
        context_manager = (
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
        return runtime, context_manager

    async def upload(
        self,
        *,
        object_id: str,
        data: bytes,
        content_type: str,
        allow_demo_fallback: bool = False,
    ) -> StoredImageEvidence:
        normalized = validate_image(
            content_type=content_type,
            data=data,
            max_bytes=self.settings.report_evidence_max_bytes,
            invalid_code=self.invalid_code,
            too_large_code=self.too_large_code,
            label=self.label,
        )
        storage_path = f"{self.namespace}/{object_id}/{uuid4()}.{_EXTENSIONS[normalized]}"
        if not self._require_configured(allow_demo_fallback=allow_demo_fallback):
            return StoredImageEvidence(storage_path, normalized, len(data), storage_mode="demo-synthetic")

        base_url = self.settings.supabase_url.rstrip("/")
        key = self.settings.supabase_service_role_key
        assert key is not None
        runtime, context_manager = self._operation_context(
            "external.supabase.storage.upload", "storage.upload", "POST"
        )
        provider_error: httpx.HTTPError | None = None
        with context_manager as span:
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    response = await client.post(
                        f"{base_url}/storage/v1/object/"
                        f"{self.settings.supabase_report_evidence_bucket}/{storage_path}",
                        headers={
                            "apikey": key,
                            "Authorization": f"Bearer {key}",
                            "Content-Type": normalized,
                            "x-upsert": "false",
                        },
                        content=data,
                    )
            except httpx.HTTPError as error:
                provider_error = error
                if runtime is not None:
                    runtime.mark_span_failed(span, exception=error)
            else:
                success = response.status_code in {status.HTTP_200_OK, status.HTTP_201_CREATED}
                if span is not None:
                    span.set_attribute("http.response.status_code", response.status_code)
                    span.set_attribute("outcome", "success" if success else "error")
                if not success and runtime is not None:
                    runtime.mark_span_failed(span, error_code=self.invalid_code)
        if provider_error is not None:
            raise image_http_error(
                self.invalid_code,
                f"{self.label} storage is unavailable.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from provider_error
        if not success:
            raise image_http_error(
                self.invalid_code,
                f"{self.label} could not be stored.",
                status.HTTP_502_BAD_GATEWAY,
            )
        return StoredImageEvidence(storage_path, normalized, len(data))

    async def create_signed_url(self, storage_path: str, *, expires_in: int = 300) -> str:
        if not self._require_configured(allow_demo_fallback=True):
            return f"demo-private://{storage_path}"

        base_url = self.settings.supabase_url.rstrip("/")
        key = self.settings.supabase_service_role_key
        assert key is not None
        runtime, context_manager = self._operation_context(
            "external.supabase.storage.sign", "storage.sign", "POST"
        )
        provider_error: httpx.HTTPError | None = None
        with context_manager as span:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        f"{base_url}/storage/v1/object/sign/"
                        f"{self.settings.supabase_report_evidence_bucket}/{storage_path}",
                        headers={"apikey": key, "Authorization": f"Bearer {key}"},
                        json={"expiresIn": expires_in},
                    )
            except httpx.HTTPError as error:
                provider_error = error
                if runtime is not None:
                    runtime.mark_span_failed(span, exception=error)
            else:
                success = response.status_code == status.HTTP_200_OK
                if span is not None:
                    span.set_attribute("http.response.status_code", response.status_code)
                    span.set_attribute("outcome", "success" if success else "error")
                if not success and runtime is not None:
                    runtime.mark_span_failed(span, error_code=self.invalid_code)
        if provider_error is not None or not success:
            raise image_http_error(
                self.invalid_code,
                f"{self.label} is temporarily unavailable.",
                status.HTTP_503_SERVICE_UNAVAILABLE if provider_error is not None else status.HTTP_502_BAD_GATEWAY,
            ) from provider_error
        payload = response.json()
        signed_url = payload.get("signedURL") or payload.get("signedUrl")
        if not isinstance(signed_url, str) or not signed_url:
            raise image_http_error(
                self.invalid_code,
                f"{self.label} is temporarily unavailable.",
                status.HTTP_502_BAD_GATEWAY,
            )
        return signed_url if signed_url.startswith("http") else f"{base_url}/storage/v1{signed_url}"

    async def delete(self, storage_path: str | None) -> bool:
        if not storage_path:
            return True
        if not self._configured():
            return self.settings.demo_mode

        base_url = self.settings.supabase_url.rstrip("/")
        key = self.settings.supabase_service_role_key
        assert key is not None
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
                        headers={"apikey": key, "Authorization": f"Bearer {key}"},
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
                    runtime.mark_span_failed(span, error_code=self.invalid_code)
        if provider_error is not None:
            return False
        return success


__all__ = [
    "ALLOWED_IMAGE_TYPES",
    "EVIDENCE_CHUNK_BYTES",
    "ImageEvidenceStorage",
    "StoredImageEvidence",
    "image_http_error",
    "read_bounded_image",
    "signature_matches",
    "validate_image",
]
