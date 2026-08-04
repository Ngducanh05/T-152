from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class AppRole(StrEnum):
    """Application roles. This is separate from Supabase's authenticated role."""

    RESIDENT = "resident"
    SECURITY = "security"
    ADMIN = "admin"


class CurrentUser(BaseModel):
    """Identity returned by the authenticated-user endpoint."""

    id: UUID
    email: str | None = None
    full_name: str | None = None
    app_role: AppRole
