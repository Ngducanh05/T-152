from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AppRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class CurrentUser(BaseModel):
    """Authenticated ParkSmart identity resolved exclusively by the backend."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    email: str | None = None
    full_name: str | None = None
    role: AppRole
    parking_user_id: str | None = None
    default_vehicle_id: str | None = None

    @property
    def app_role(self) -> AppRole:
        """Compatibility alias for backend code that still reads app_role."""
        return self.role
