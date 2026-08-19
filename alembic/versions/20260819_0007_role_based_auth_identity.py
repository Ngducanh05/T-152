"""Normalize application roles and link profiles to parking identities.

Revision ID: 20260819_0007
Revises: 20260819_0006
Create Date: 2026-08-19
"""

import sqlalchemy as sa

from alembic import op

revision = "20260819_0007"
down_revision = "20260819_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Migrate legacy roles and add optional ParkSmart business identity links.

    Existing resident/security profiles deliberately become regular users.  The
    new parking identity columns stay nullable during migration because the
    database cannot safely guess which ParkingUser belongs to an Auth UUID.
    Runtime authorization rejects user profiles until an operator links them.
    """
    op.execute("ALTER TABLE profiles ALTER COLUMN app_role DROP DEFAULT")
    op.execute("ALTER TYPE app_role_enum RENAME TO app_role_enum_legacy")
    op.execute("CREATE TYPE app_role_enum AS ENUM ('user', 'admin')")
    op.execute(
        """
        ALTER TABLE profiles
        ALTER COLUMN app_role TYPE app_role_enum
        USING (
            CASE
                WHEN app_role::text = 'admin' THEN 'admin'
                ELSE 'user'
            END
        )::app_role_enum
        """
    )
    op.execute(
        "ALTER TABLE profiles ALTER COLUMN app_role "
        "SET DEFAULT 'user'::app_role_enum"
    )
    op.execute("DROP TYPE app_role_enum_legacy")

    op.add_column(
        "profiles",
        sa.Column("parking_user_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "profiles",
        sa.Column("default_vehicle_id", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_profiles_parking_user_id_parking_users",
        "profiles",
        "parking_users",
        ["parking_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_profiles_default_vehicle_id_vehicles",
        "profiles",
        "vehicles",
        ["default_vehicle_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_profiles_parking_user_id",
        "profiles",
        ["parking_user_id"],
    )
    op.create_index(
        "ix_profiles_default_vehicle_id",
        "profiles",
        ["default_vehicle_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_profiles_default_vehicle_id", table_name="profiles")
    op.drop_constraint("uq_profiles_parking_user_id", "profiles", type_="unique")
    op.drop_constraint(
        "fk_profiles_default_vehicle_id_vehicles",
        "profiles",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_profiles_parking_user_id_parking_users",
        "profiles",
        type_="foreignkey",
    )
    op.drop_column("profiles", "default_vehicle_id")
    op.drop_column("profiles", "parking_user_id")

    op.execute("ALTER TABLE profiles ALTER COLUMN app_role DROP DEFAULT")
    op.execute("ALTER TYPE app_role_enum RENAME TO app_role_enum_phase11")
    op.execute(
        "CREATE TYPE app_role_enum AS ENUM ('resident', 'security', 'admin')"
    )
    op.execute(
        """
        ALTER TABLE profiles
        ALTER COLUMN app_role TYPE app_role_enum
        USING (
            CASE
                WHEN app_role::text = 'admin' THEN 'admin'
                ELSE 'resident'
            END
        )::app_role_enum
        """
    )
    op.execute(
        "ALTER TABLE profiles ALTER COLUMN app_role "
        "SET DEFAULT 'resident'::app_role_enum"
    )
    op.execute("DROP TYPE app_role_enum_phase11")
