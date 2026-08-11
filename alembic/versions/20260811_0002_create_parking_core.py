"""Create ParkSmart parking core tables.

Revision ID: 20260811_0002
Revises: 20260804_0001
Create Date: 2026-08-11
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260811_0002"
down_revision = "20260804_0001"
branch_labels = None
depends_on = None


map_node_type_enum = postgresql.ENUM(
    "ENTRANCE", "EXIT", "CHECKPOINT", "ELEVATOR", "AISLE", "SLOT",
    name="map_node_type_enum",
    create_type=False,
)
slot_status_enum = postgresql.ENUM(
    "AVAILABLE", "RESERVED", "OCCUPIED",
    name="slot_status_enum",
    create_type=False,
)
reservation_status_enum = postgresql.ENUM(
    "ACTIVE", "CONFIRMED", "EXPIRED", "CANCELLED",
    name="reservation_status_enum",
    create_type=False,
)
parking_session_status_enum = postgresql.ENUM(
    "ACTIVE", "COMPLETED", "CANCELLED",
    name="parking_session_status_enum",
    create_type=False,
)
parking_event_type_enum = postgresql.ENUM(
    "VEHICLE_ENTERED",
    "SLOT_RESERVED",
    "RESERVATION_CANCELLED",
    "RESERVATION_EXPIRED",
    "VEHICLE_PARKED",
    "VEHICLE_LEFT_SLOT",
    "VEHICLE_EXITED",
    name="parking_event_type_enum",
    create_type=False,
)
actor_type_enum = postgresql.ENUM(
    "USER", "SIMULATOR", "CAMERA", "SYSTEM",
    name="actor_type_enum",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in (
        map_node_type_enum,
        slot_status_enum,
        reservation_status_enum,
        parking_session_status_enum,
        parking_event_type_enum,
        actor_type_enum,
    ):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "map_nodes",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("floor_id", sa.String(length=16), nullable=False),
        sa.Column("type", map_node_type_enum, nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.CheckConstraint("floor_id = 'F1'", name="ck_map_nodes_floor_f1"),
        sa.CheckConstraint("id LIKE 'F1-%'", name="ck_map_nodes_id_f1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_map_nodes_floor_id", "map_nodes", ["floor_id"])
    op.create_index("ix_map_nodes_type", "map_nodes", ["type"])

    op.create_table(
        "parking_users",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("current_node_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["current_node_id"], ["map_nodes.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_parking_users_current_node_id", "parking_users", ["current_node_id"])

    op.create_table(
        "vehicles",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("plate_number", sa.String(length=32), nullable=False),
        sa.Column("requires_charging", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["parking_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plate_number"),
    )
    op.create_index("ix_vehicles_user_id", "vehicles", ["user_id"])

    op.create_table(
        "map_edges",
        sa.Column("from_node", sa.String(length=64), nullable=False),
        sa.Column("to_node", sa.String(length=64), nullable=False),
        sa.Column("distance_m", sa.Float(), nullable=False),
        sa.Column("bidirectional", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint("distance_m > 0", name="ck_map_edges_positive_distance"),
        sa.CheckConstraint("from_node <> to_node", name="ck_map_edges_distinct_nodes"),
        sa.ForeignKeyConstraint(["from_node"], ["map_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_node"], ["map_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("from_node", "to_node"),
    )
    op.create_index("ix_map_edges_to_node", "map_edges", ["to_node"])

    op.create_table(
        "parking_slots",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("floor_id", sa.String(length=16), nullable=False),
        sa.Column("zone_id", sa.String(length=16), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            slot_status_enum,
            server_default=sa.text("'AVAILABLE'"),
            nullable=False,
        ),
        sa.Column("has_charger", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_accessible", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("occupied_by_vehicle_id", sa.String(length=64), nullable=True),
        sa.CheckConstraint("floor_id = 'F1'", name="ck_parking_slots_floor_f1"),
        sa.CheckConstraint("id LIKE 'F1-%'", name="ck_parking_slots_id_f1"),
        sa.CheckConstraint("version >= 0", name="ck_parking_slots_version_nonnegative"),
        sa.CheckConstraint(
            "zone_id IN ('A', 'B', 'C', 'D')", name="ck_parking_slots_zone"
        ),
        sa.ForeignKeyConstraint(["node_id"], ["map_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["occupied_by_vehicle_id"], ["vehicles.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_parking_slots_node_id", "parking_slots", ["node_id"])
    op.create_index(
        "ix_parking_slots_occupied_by_vehicle_id",
        "parking_slots",
        ["occupied_by_vehicle_id"],
    )
    op.create_index("ix_parking_slots_status_zone", "parking_slots", ["status", "zone_id"])

    op.create_table(
        "parking_reservations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("vehicle_id", sa.String(length=64), nullable=False),
        sa.Column("slot_id", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            reservation_status_enum,
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_reservations_expiry_after_creation"
        ),
        sa.ForeignKeyConstraint(["slot_id"], ["parking_slots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["parking_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_parking_reservations_active_slot",
        "parking_reservations",
        ["slot_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "uq_parking_reservations_active_user",
        "parking_reservations",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "uq_parking_reservations_active_vehicle",
        "parking_reservations",
        ["vehicle_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "parking_sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("vehicle_id", sa.String(length=64), nullable=False),
        sa.Column("slot_id", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            parking_session_status_enum,
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
        sa.Column(
            "parked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= parked_at",
            name="ck_sessions_completed_after_parked",
        ),
        sa.ForeignKeyConstraint(["slot_id"], ["parking_slots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["parking_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_parking_sessions_active_slot",
        "parking_sessions",
        ["slot_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "uq_parking_sessions_active_user",
        "parking_sessions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "uq_parking_sessions_active_vehicle",
        "parking_sessions",
        ["vehicle_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

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

    op.create_table(
        "parking_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("event_type", parking_event_type_enum, nullable=False),
        sa.Column("slot_id", sa.String(length=64), nullable=True),
        sa.Column("actor_type", actor_type_enum, nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("old_status", slot_status_enum, nullable=True),
        sa.Column("new_status", slot_status_enum, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["slot_id"], ["parking_slots.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_parking_events_event_type", "parking_events", ["event_type"])
    op.create_index(
        "ix_parking_events_slot_created", "parking_events", ["slot_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("parking_events")
    op.drop_table("location_checkpoints")
    op.drop_table("parking_sessions")
    op.drop_table("parking_reservations")
    op.drop_table("parking_slots")
    op.drop_table("map_edges")
    op.drop_table("vehicles")
    op.drop_table("parking_users")
    op.drop_table("map_nodes")

    bind = op.get_bind()
    for enum_type in (
        actor_type_enum,
        parking_event_type_enum,
        parking_session_status_enum,
        reservation_status_enum,
        slot_status_enum,
        map_node_type_enum,
    ):
        enum_type.drop(bind, checkfirst=True)
