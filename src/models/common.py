from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    """Consistent successful API response envelope."""

    success: bool = True
    data: T
    message: str | None = None


class ErrorDetail(BaseModel):
    """Public, non-sensitive error details."""

    code: str
    message: str
    details: dict[str, object] | None = None


class ErrorResponse(BaseModel):
    """Consistent failed API response envelope."""

    success: bool = False
    error: ErrorDetail
