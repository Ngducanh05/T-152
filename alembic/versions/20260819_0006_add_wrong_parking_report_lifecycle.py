"""Add lifecycle fields to wrong-parking reports.

Revision ID: 20260819_0006
Revises: 20260815_0005
Create Date: 2026-08-19
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260819_0006"
down_revision = "20260815_0005"
branch_labels = None
depends_on = None


wrong_parking_reason_enum = postgresql.ENUM(
    "WRONG_SLOT",
    "CROSSED_LINE",
    "BLOCKING_ACCESS",
    "OCCUPYING_CHARGER",
    "OTHER",
    name="wrong_parking_reason_enum",
    create_type=False,
)
wrong_parking_report_status_enum = postgresql.ENUM(
    "OPEN",
    "RESOLVED",
    name="wrong_parking_report_status_enum",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    wrong_parking_reason_enum.create(bind, checkfirst=True)
    wrong_parking_report_status_enum.create(bind, checkfirst=True)

    op.add_column(
        "wrong_parking_reports",
        sa.Column("reason_code", wrong_parking_reason_enum, nullable=True),
    )
    op.add_column(
        "wrong_parking_reports",
        sa.Column("status", wrong_parking_report_status_enum, nullable=True),
    )
    op.add_column(
        "wrong_parking_reports",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "wrong_parking_reports",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "wrong_parking_reports",
        sa.Column("resolved_by", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "wrong_parking_reports",
        sa.Column("resolution_note", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "wrong_parking_reports",
        sa.Column("version", sa.Integer(), nullable=True),
    )
    op.alter_column(
        "wrong_parking_reports",
        "description",
        existing_type=sa.String(length=500),
        nullable=True,
    )

    op.execute(
        sa.text(
            """
            UPDATE wrong_parking_reports
            SET reason_code = 'OTHER',
                status = 'OPEN',
                version = 0,
                updated_at = created_at
            """
        )
    )

    op.alter_column(
        "wrong_parking_reports",
        "reason_code",
        existing_type=wrong_parking_reason_enum,
        nullable=False,
        server_default=sa.text("'OTHER'"),
    )
    op.alter_column(
        "wrong_parking_reports",
        "status",
        existing_type=wrong_parking_report_status_enum,
        nullable=False,
        server_default=sa.text("'OPEN'"),
    )
    op.alter_column(
        "wrong_parking_reports",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    op.alter_column(
        "wrong_parking_reports",
        "version",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("0"),
    )
    op.create_check_constraint(
        "ck_wrong_parking_reports_version_nonnegative",
        "wrong_parking_reports",
        "version >= 0",
    )
    op.create_index(
        "ix_wrong_parking_reports_status_created",
        "wrong_parking_reports",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_wrong_parking_reports_slot_status_created",
        "wrong_parking_reports",
        ["slot_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_wrong_parking_reports_slot_status_created",
        table_name="wrong_parking_reports",
    )
    op.drop_index(
        "ix_wrong_parking_reports_status_created",
        table_name="wrong_parking_reports",
    )
    op.drop_constraint(
        "ck_wrong_parking_reports_version_nonnegative",
        "wrong_parking_reports",
        type_="check",
    )

    # Revision 0005 requires a non-null description. Preserve every row while
    # restoring that older shape for reports created under revision 0006.
    op.execute(
        sa.text(
            "UPDATE wrong_parking_reports SET description = '' "
            "WHERE description IS NULL"
        )
    )
    op.alter_column(
        "wrong_parking_reports",
        "description",
        existing_type=sa.String(length=500),
        nullable=False,
    )

    op.drop_column("wrong_parking_reports", "version")
    op.drop_column("wrong_parking_reports", "resolution_note")
    op.drop_column("wrong_parking_reports", "resolved_by")
    op.drop_column("wrong_parking_reports", "resolved_at")
    op.drop_column("wrong_parking_reports", "updated_at")
    op.drop_column("wrong_parking_reports", "status")
    op.drop_column("wrong_parking_reports", "reason_code")

    bind = op.get_bind()
    wrong_parking_report_status_enum.drop(bind, checkfirst=True)
    wrong_parking_reason_enum.drop(bind, checkfirst=True)
