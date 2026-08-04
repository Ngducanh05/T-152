from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class AppRole(StrEnum):
<<<<<<< HEAD
    """Application roles. This is separate from Supabase's authenticated role."""

=======
>>>>>>> 7bfdef8664e5fb388c432168789d837cc6c3dcb0
    RESIDENT = "resident"
    SECURITY = "security"
    ADMIN = "admin"


class CurrentUser(BaseModel):
<<<<<<< HEAD
    """Identity returned by the authenticated-user endpoint."""

    id: UUID
    email: str | None = None
    full_name: str | None = None
    app_role: AppRole
=======
    id: UUID
    email: str | None = None
    full_name: str | None = None
    app_role: AppRole
>>>>>>> 7bfdef8664e5fb388c432168789d837cc6c3dcb0
