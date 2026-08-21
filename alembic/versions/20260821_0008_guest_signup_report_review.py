"""Add onboarding support fields for report evidence and review.

Revision ID: 20260821_0008
Revises: 20260819_0007
Create Date: 2026-08-21
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260821_0008"
down_revision = "20260819_0007"
branch_labels = None
depends_on = None


wrong_parking_review_status_enum = postgresql.ENUM(
    "PENDING",
    "CONFIRMED",
    "REJECTED",
    name="wrong_parking_review_status_enum",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    wrong_parking_review_status_enum.create(bind, checkfirst=True)

    op.add_column(
        "wrong_parking_reports",
        sa.Column(
            "review_status",
            wrong_parking_review_status_enum,
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
    )
    op.add_column(
        "wrong_parking_reports",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "wrong_parking_reports",
        sa.Column("reviewed_by", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "wrong_parking_reports",
        sa.Column("review_note", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "wrong_parking_reports",
        sa.Column("evidence_storage_path", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "wrong_parking_reports",
        sa.Column("evidence_content_type", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "wrong_parking_reports",
        sa.Column("evidence_size_bytes", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_wrong_parking_reports_review_status_created",
        "wrong_parking_reports",
        ["review_status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_wrong_parking_reports_review_status_created",
        table_name="wrong_parking_reports",
    )
    op.drop_column("wrong_parking_reports", "evidence_size_bytes")
    op.drop_column("wrong_parking_reports", "evidence_content_type")
    op.drop_column("wrong_parking_reports", "evidence_storage_path")
    op.drop_column("wrong_parking_reports", "review_note")
    op.drop_column("wrong_parking_reports", "reviewed_by")
    op.drop_column("wrong_parking_reports", "reviewed_at")
    op.drop_column("wrong_parking_reports", "review_status")

    bind = op.get_bind()
    wrong_parking_review_status_enum.drop(bind, checkfirst=True)
