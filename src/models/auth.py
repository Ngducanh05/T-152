from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class AppRole(StrEnum):
    RESIDENT = "resident"
    SECURITY = "security"
    ADMIN = "admin"


class CurrentUser(BaseModel):
    id: UUID
    email: str | None = None
    full_name: str | None = None
    app_role: AppRole
