from io import StringIO
from unittest.mock import Mock, patch

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.dialects.postgresql import JSONB

from alembic import command
from src.core import database as core_database
from src.core.db_models import Base, ParkingEvent, ParkingSlot, Profile
from src.models.schemas import ParkingSlot as ParkingSlotSchema
from src.services import database as compatibility_database
from src.services import db_models as compatibility_models

EXPECTED_TABLES = {
    "profiles",
    "parking_users",
    "vehicles",
    "map_nodes",
    "map_edges",
    "parking_slots",
    "parking_reservations",
    "parking_sessions",
    "parking_events",
}


def test_services_reexport_canonical_database_objects():
    assert compatibility_database.get_engine is core_database.get_engine
    assert compatibility_database.get_session_factory is core_database.get_session_factory
    assert compatibility_database.get_db_session is core_database.get_db_session
    assert compatibility_models.Base is Base
    assert compatibility_models.Profile is Profile


def test_single_metadata_contains_profile_and_parking_tables():
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    assert Profile.metadata is Base.metadata
    assert ParkingSlot.metadata is Base.metadata


def test_parking_migration_follows_profiles_revision():
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    parking_revision = scripts.get_revision("20260811_0002")

    location_cleanup_revision = scripts.get_revision("20260812_0003")
    nearest_aisle_revision = scripts.get_revision("20260813_0004")

    assert scripts.get_current_head() == "20260813_0004"
    assert parking_revision is not None
    assert parking_revision.down_revision == "20260804_0001"
    assert location_cleanup_revision is not None
    assert location_cleanup_revision.down_revision == "20260811_0002"
    assert nearest_aisle_revision is not None
    assert nearest_aisle_revision.down_revision == "20260812_0003"


def test_cold_start_sql_creates_profile_enum_once():
    output = StringIO()
    config = Config("alembic.ini", output_buffer=output)
    config.attributes["configure_logger"] = False

    command.upgrade(config, "head", sql=True)

    assert output.getvalue().count("CREATE TYPE app_role_enum") == 1


def test_nearest_aisle_data_migration_is_noop_before_canonical_seed():
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = scripts.get_revision("20260813_0004")
    assert revision is not None
    migration = revision.module
    bind = Mock()
    bind.execute.return_value.scalars.return_value = []

    with (
        patch.object(migration.context, "is_offline_mode", return_value=False),
        patch.object(migration.op, "get_bind", return_value=bind),
        patch.object(migration.op, "execute") as execute,
        patch.object(migration.op, "bulk_insert") as bulk_insert,
    ):
        migration.upgrade()

    assert bind.execute.call_count == 2
    execute.assert_not_called()
    bulk_insert.assert_not_called()


def test_nearest_aisle_data_migration_rewrites_seeded_canonical_slots():
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = scripts.get_revision("20260813_0004")
    assert revision is not None
    migration = revision.module
    slot_ids = {
        f"F1-{zone}{slot_number:02d}"
        for zone in "ABCD"
        for slot_number in range(1, 11)
    }
    node_ids = slot_ids | {
        f"F1-{zone}-{side}" for zone in "ABCD" for side in ("W", "E")
    }
    slot_result = Mock()
    slot_result.scalars.return_value = slot_ids
    node_result = Mock()
    node_result.scalars.return_value = node_ids
    bind = Mock()
    bind.execute.side_effect = [slot_result, node_result]

    with (
        patch.object(migration.context, "is_offline_mode", return_value=False),
        patch.object(migration.op, "get_bind", return_value=bind),
        patch.object(migration.op, "execute") as execute,
        patch.object(migration.op, "bulk_insert") as bulk_insert,
    ):
        migration.upgrade()

    assert execute.call_count == 41  # one edge delete and forty slot updates
    bulk_insert.assert_called_once()
    inserted_edges = bulk_insert.call_args.args[1]
    assert len(inserted_edges) == 40
    assert {
        (edge["from_node"], edge["to_node"]) for edge in inserted_edges
    } >= {
        ("F1-A-W", "F1-A01"),
        ("F1-A-E", "F1-A04"),
        ("F1-D-W", "F1-D08"),
        ("F1-D-E", "F1-D10"),
    }


def test_parking_event_avoids_reserved_metadata_attribute():
    assert "event_metadata" in ParkingEvent.__mapper__.attrs
    assert "metadata" not in ParkingEvent.__mapper__.attrs
    assert ParkingEvent.__table__.c.metadata.name == "metadata"
    assert isinstance(ParkingEvent.__table__.c.metadata.type, JSONB)


def test_active_reservation_and_session_indexes_are_partial_and_unique():
    for table_name in ("parking_reservations", "parking_sessions"):
        indexes = Base.metadata.tables[table_name].indexes
        active_indexes = [index for index in indexes if index.name and "_active_" in index.name]

        assert len(active_indexes) == 3
        assert all(index.unique for index in active_indexes)
        assert all(index.dialect_options["postgresql"]["where"] is not None for index in active_indexes)


def test_parking_slot_contract_exposes_nullable_occupying_vehicle():
    slot = ParkingSlotSchema(
        id="F1-C03",
        floor_id="F1",
        zone_id="C",
        node_id="F1-C-W",
        status="AVAILABLE",
        has_charger=True,
        is_accessible=False,
        version=0,
    )

    assert slot.occupied_by_vehicle_id is None
    assert "occupied_by_vehicle_id" in ParkingSlot.__table__.c


def test_multiple_slots_can_reference_the_same_aisle_node():
    node_id = ParkingSlot.__table__.c.node_id

    assert node_id.index is True
    assert node_id.unique is not True
