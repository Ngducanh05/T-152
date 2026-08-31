"""Add optional private evidence metadata to slot observations."""

import sqlalchemy as sa

from alembic import op

revision = "20260831_0017"
down_revision = "20260830_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("slot_observations", sa.Column("evidence_storage_path", sa.String(length=512), nullable=True))
    op.add_column("slot_observations", sa.Column("evidence_content_type", sa.String(length=100), nullable=True))
    op.add_column("slot_observations", sa.Column("evidence_size_bytes", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_slot_observations_evidence_size_nonnegative",
        "slot_observations",
        "evidence_size_bytes IS NULL OR evidence_size_bytes >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_slot_observations_evidence_size_nonnegative", "slot_observations", type_="check")
    op.drop_column("slot_observations", "evidence_size_bytes")
    op.drop_column("slot_observations", "evidence_content_type")
    op.drop_column("slot_observations", "evidence_storage_path")
