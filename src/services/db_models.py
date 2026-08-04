import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for ParkSmart SQLAlchemy ORM entities."""


class AppRoleEnum(StrEnum):
    RESIDENT = "resident"
    SECURITY = "security"
    ADMIN = "admin"


class Profile(Base):
    """ParkSmart profile linked one-to-one with a Supabase Auth user."""

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    app_role: Mapped[AppRoleEnum] = mapped_column(
        Enum(
            AppRoleEnum,
            name="app_role_enum",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=False,
        default=AppRoleEnum.RESIDENT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
