from typing import Generic, TypeVar

from pydantic import BaseModel

from src.models.schemas import ErrorCode

T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T
    message: str | None = None


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    request_id: str
    details: dict[str, object] | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail
