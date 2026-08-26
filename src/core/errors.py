"""Stable domain-error protocol shared by Core Services and API boundaries."""

from src.models.schemas import ErrorCode


class DomainError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


__all__ = ["DomainError"]
