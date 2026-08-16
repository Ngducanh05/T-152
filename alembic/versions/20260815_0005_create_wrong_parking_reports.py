"""Create user wrong-parking reports.

Revision ID: 20260815_0005
Revises: 20260813_0004
Create Date: 2026-08-15
"""

import sqlalchemy as sa

from alembic import op

revision = "20260815_0005"
down_revision = "20260813_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wrong_parking_reports",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("reporter_user_id", sa.String(length=64), nullable=False),
        sa.Column("slot_id", sa.String(length=64), nullable=False),
        sa.Column("observed_plate_number", sa.String(length=32), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["reporter_user_id"], ["parking_users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["slot_id"], ["parking_slots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wrong_parking_reports_created",
        "wrong_parking_reports",
        ["created_at"],
    )
    op.create_index(
        "ix_wrong_parking_reports_reporter_user_id",
        "wrong_parking_reports",
        ["reporter_user_id"],
    )
    op.create_index(
        "ix_wrong_parking_reports_slot_created",
        "wrong_parking_reports",
        ["slot_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("wrong_parking_reports")
