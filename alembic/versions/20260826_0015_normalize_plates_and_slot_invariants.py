"""Normalize vehicle identity and strengthen map/slot invariants.

Revision ID: 20260826_0015
Revises: 20260826_0014
Create Date: 2026-08-26
"""

import sqlalchemy as sa

from alembic import op

revision = "20260826_0015"
down_revision = "20260826_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vehicles",
        sa.Column("normalized_plate_number", sa.String(length=32), nullable=True),
    )
    op.execute(
        """
        UPDATE vehicles
        SET normalized_plate_number = upper(
            regexp_replace(plate_number, '[[:space:]._-]+', '', 'g')
        )
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM vehicles
                GROUP BY normalized_plate_number
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'vehicle plates collide after canonical normalization';
            END IF;
        END $$
        """
    )
    op.alter_column("vehicles", "normalized_plate_number", nullable=False)
    op.drop_constraint("vehicles_plate_number_key", "vehicles", type_="unique")
    op.create_unique_constraint(
        "uq_vehicles_normalized_plate_number",
        "vehicles",
        ["normalized_plate_number"],
    )

    op.drop_constraint(
        "ck_parking_slots_id_floor_prefix", "parking_slots", type_="check"
    )
    op.create_check_constraint(
        "ck_parking_slots_id_canonical",
        "parking_slots",
        "id ~ '^F[1-3]-[A-D](0[1-9]|10)$'",
    )
    op.create_check_constraint(
        "ck_parking_slots_id_matches_floor",
        "parking_slots",
        "substring(id from 1 for 2) = floor_id",
    )
    op.create_check_constraint(
        "ck_parking_slots_id_matches_zone",
        "parking_slots",
        "substring(id from 4 for 1) = zone_id",
    )
    op.create_check_constraint(
        "ck_map_nodes_id_matches_floor",
        "map_nodes",
        "substring(id from 1 for 2) = floor_id",
    )


def downgrade() -> None:
    op.drop_constraint("ck_map_nodes_id_matches_floor", "map_nodes", type_="check")
    op.drop_constraint(
        "ck_parking_slots_id_matches_zone", "parking_slots", type_="check"
    )
    op.drop_constraint(
        "ck_parking_slots_id_matches_floor", "parking_slots", type_="check"
    )
    op.drop_constraint("ck_parking_slots_id_canonical", "parking_slots", type_="check")
    op.create_check_constraint(
        "ck_parking_slots_id_floor_prefix",
        "parking_slots",
        "id ~ '^F[1-3]-'",
    )
    op.drop_constraint(
        "uq_vehicles_normalized_plate_number", "vehicles", type_="unique"
    )
    op.create_unique_constraint("vehicles_plate_number_key", "vehicles", ["plate_number"])
    op.drop_column("vehicles", "normalized_plate_number")
