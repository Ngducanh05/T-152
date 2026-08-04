from typing import Generic, TypeVar

from pydantic import BaseModel

<<<<<<< HEAD
=======

>>>>>>> 7bfdef8664e5fb388c432168789d837cc6c3dcb0
T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
<<<<<<< HEAD
    """Consistent successful API response envelope."""

=======
>>>>>>> 7bfdef8664e5fb388c432168789d837cc6c3dcb0
    success: bool = True
    data: T
    message: str | None = None


class ErrorDetail(BaseModel):
<<<<<<< HEAD
    """Public, non-sensitive error details."""

    code: str
    message: str
    details: dict[str, object] | None = None


class ErrorResponse(BaseModel):
    """Consistent failed API response envelope."""

    success: bool = False
    error: ErrorDetail
=======
    code: str
    message: str
    details: dict | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail
>>>>>>> 7bfdef8664e5fb388c432168789d837cc6c3dcb0
