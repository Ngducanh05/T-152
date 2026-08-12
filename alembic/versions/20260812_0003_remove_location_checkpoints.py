"""Remove the redundant location checkpoint table.

Checkpoint and parking-slot locations are resolved directly from map_nodes and
parking_slots by their canonical IDs.

Revision ID: 20260812_0003
Revises: 20260811_0002
Create Date: 2026-08-12
"""

import sqlalchemy as sa

from alembic import op

revision = "20260812_0003"
down_revision = "20260811_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("location_checkpoints")


def downgrade() -> None:
    op.create_table(
        "location_checkpoints",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=False),
        sa.Column("qr_payload", sa.String(length=255), nullable=False),
        sa.CheckConstraint("id LIKE 'F1-%'", name="ck_checkpoints_id_f1"),
        sa.ForeignKeyConstraint(["node_id"], ["map_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id"),
        sa.UniqueConstraint("qr_payload"),
    )
