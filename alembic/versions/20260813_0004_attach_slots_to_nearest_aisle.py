"""Attach parking slots to the nearest aisle endpoint.

Revision ID: 20260813_0004
Revises: 20260812_0003
Create Date: 2026-08-13
"""

from collections.abc import Callable

import sqlalchemy as sa

from alembic import op

revision = "20260813_0004"
down_revision = "20260812_0003"
branch_labels = None
depends_on = None


slot_table = sa.table(
    "parking_slots",
    sa.column("id", sa.String),
    sa.column("node_id", sa.String),
)
edge_table = sa.table(
    "map_edges",
    sa.column("from_node", sa.String),
    sa.column("to_node", sa.String),
    sa.column("distance_m", sa.Float),
    sa.column("bidirectional", sa.Boolean),
    sa.column("enabled", sa.Boolean),
)


def _side_for_nearest_aisle(slot_number: int) -> str:
    position_in_row = (slot_number - 1) % 5 + 1
    return "W" if position_in_row <= 3 else "E"


def _side_for_legacy_aisle(slot_number: int) -> str:
    return "W" if slot_number <= 5 else "E"


def _replace_slot_attachments(side_resolver: Callable[[int], str]) -> None:
    # Slot edges are always stored aisle -> slot in the canonical graph.
    op.execute(
        sa.delete(edge_table).where(
            edge_table.c.to_node.op("~")(r"^F1-[A-D][0-9]{2}$")
        )
    )

    new_edges: list[dict[str, object]] = []
    for zone in "ABCD":
        for slot_number in range(1, 11):
            slot_id = f"F1-{zone}{slot_number:02d}"
            side = side_resolver(slot_number)
            aisle_id = f"F1-{zone}-{side}"
            op.execute(
                sa.update(slot_table)
                .where(slot_table.c.id == slot_id)
                .values(node_id=aisle_id)
            )
            new_edges.append(
                {
                    "from_node": aisle_id,
                    "to_node": slot_id,
                    "distance_m": 4.0,
                    "bidirectional": True,
                    "enabled": True,
                }
            )
    op.bulk_insert(edge_table, new_edges)


def upgrade() -> None:
    _replace_slot_attachments(_side_for_nearest_aisle)


def downgrade() -> None:
    _replace_slot_attachments(_side_for_legacy_aisle)
