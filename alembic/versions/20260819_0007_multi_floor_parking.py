"""Phase 11: Multi-floor parking (F1-F3).

Revision ID: 0007
Revises: 20260819_0006_add_wrong_parking_report_lifecycle
Create Date: 2026-08-19

Expands constraints and enum types to support three parking floors (F1, F2, F3)
with ramp and elevator inter-floor connectors.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0007"
down_revision = "20260819_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- 1. Add RAMP to map_node_type_enum ---
    op.execute("ALTER TYPE map_node_type_enum ADD VALUE IF NOT EXISTS 'RAMP'")

    # --- 2. Create route_mode_enum type ---
    route_mode_enum = sa.Enum("VEHICLE", "PEDESTRIAN", name="route_mode_enum")
    route_mode_enum.create(op.get_bind(), checkfirst=True)

    # --- 3. Add allowed_mode column to map_edges ---
    op.add_column(
        "map_edges",
        sa.Column(
            "allowed_mode",
            sa.Enum("VEHICLE", "PEDESTRIAN", name="route_mode_enum", create_type=False),
            nullable=True,
        ),
    )

    # --- 4. Drop old F1-only constraints on map_nodes ---
    op.drop_constraint("ck_map_nodes_id_f1", "map_nodes", type_="check")
    op.drop_constraint("ck_map_nodes_floor_f1", "map_nodes", type_="check")

    # --- 5. Add new F1-F3 constraints on map_nodes ---
    op.create_check_constraint(
        "ck_map_nodes_id_floor_prefix",
        "map_nodes",
        "id ~ '^F[1-3]-'",
    )
    op.create_check_constraint(
        "ck_map_nodes_floor",
        "map_nodes",
        "floor_id IN ('F1', 'F2', 'F3')",
    )

    # --- 6. Drop old F1-only constraints on parking_slots ---
    op.drop_constraint("ck_parking_slots_id_f1", "parking_slots", type_="check")
    op.drop_constraint("ck_parking_slots_floor_f1", "parking_slots", type_="check")

    # --- 7. Add new F1-F3 constraints on parking_slots ---
    op.create_check_constraint(
        "ck_parking_slots_id_floor_prefix",
        "parking_slots",
        "id ~ '^F[1-3]-'",
    )
    op.create_check_constraint(
        "ck_parking_slots_floor",
        "parking_slots",
        "floor_id IN ('F1', 'F2', 'F3')",
    )

    # --- 8. Add composite index for floor + status ---
    op.create_index(
        "ix_parking_slots_floor_status",
        "parking_slots",
        ["floor_id", "status"],
    )


def downgrade() -> None:
    # Remove composite index
    op.drop_index("ix_parking_slots_floor_status", table_name="parking_slots")

    # Restore old F1-only constraints on parking_slots
    op.drop_constraint("ck_parking_slots_id_floor_prefix", "parking_slots", type_="check")
    op.drop_constraint("ck_parking_slots_floor", "parking_slots", type_="check")
    op.create_check_constraint(
        "ck_parking_slots_id_f1",
        "parking_slots",
        "id LIKE 'F1-%'",
    )
    op.create_check_constraint(
        "ck_parking_slots_floor_f1",
        "parking_slots",
        "floor_id = 'F1'",
    )

    # Restore old F1-only constraints on map_nodes
    op.drop_constraint("ck_map_nodes_id_floor_prefix", "map_nodes", type_="check")
    op.drop_constraint("ck_map_nodes_floor", "map_nodes", type_="check")
    op.create_check_constraint(
        "ck_map_nodes_id_f1",
        "map_nodes",
        "id LIKE 'F1-%'",
    )
    op.create_check_constraint(
        "ck_map_nodes_floor_f1",
        "map_nodes",
        "floor_id = 'F1'",
    )

    # Remove allowed_mode column
    op.drop_column("map_edges", "allowed_mode")

    # Drop route_mode_enum type
    sa.Enum(name="route_mode_enum").drop(op.get_bind(), checkfirst=True)

    # Note: Cannot remove RAMP from map_node_type_enum in PostgreSQL
    # without recreating the type. Left in place for safety.
