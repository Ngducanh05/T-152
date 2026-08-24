"""Add persistent per-user wrong-parking report daily usage.

Revision ID: 20260824_0012
Revises: 20260824_0011
Create Date: 2026-08-24
"""

import sqlalchemy as sa

from alembic import op

revision = "20260824_0012"
down_revision = "20260824_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_daily_usage",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column(
            "submission_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "submission_count >= 0",
            name="ck_report_daily_usage_submission_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["parking_users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "usage_date"),
    )
    op.create_index(
        "ix_report_daily_usage_usage_date",
        "report_daily_usage",
        ["usage_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_report_daily_usage_usage_date",
        table_name="report_daily_usage",
    )
    op.drop_table("report_daily_usage")
