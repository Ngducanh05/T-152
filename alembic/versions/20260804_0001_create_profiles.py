"""Create ParkSmart profiles table.

Revision ID: 20260804_0001
Revises:
Create Date: 2026-08-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260804_0001"
down_revision = None
branch_labels = None
depends_on = None


app_role_enum = sa.Enum(
    "resident",
    "security",
    "admin",
    name="app_role_enum",
)


def upgrade() -> None:
    app_role_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column(
            "app_role",
            app_role_enum,
            nullable=False,
            server_default=sa.text("'resident'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_profiles_app_role", "profiles", ["app_role"])


def downgrade() -> None:
    op.drop_index("ix_profiles_app_role", table_name="profiles")
    op.drop_table("profiles")
    app_role_enum.drop(op.get_bind(), checkfirst=True)
