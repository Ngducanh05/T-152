"""Add trusted QR-verified location state to parking users.

Revision ID: 20260826_0013
Revises: 20260824_0012
Create Date: 2026-08-26
"""

import sqlalchemy as sa

from alembic import op

revision = "20260826_0013"
down_revision = "20260824_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "parking_users",
        sa.Column("verified_node_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "parking_users",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "parking_users",
        sa.Column("verified_marker_id", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_parking_users_verified_node_id_map_nodes",
        "parking_users",
        "map_nodes",
        ["verified_node_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_parking_users_verified_node_id",
        "parking_users",
        ["verified_node_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_parking_users_verified_node_id", table_name="parking_users")
    op.drop_constraint(
        "fk_parking_users_verified_node_id_map_nodes",
        "parking_users",
        type_="foreignkey",
    )
    op.drop_column("parking_users", "verified_marker_id")
    op.drop_column("parking_users", "verified_at")
    op.drop_column("parking_users", "verified_node_id")
