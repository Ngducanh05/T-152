from datetime import UTC, datetime
from io import StringIO
from unittest.mock import Mock, patch

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import JSONB

from alembic import command
from src.core import database as core_database
from src.core.db_models import (
    AgentDailyUsage,
    Base,
    IdempotencyRecord,
    MapNode,
    ParkingEvent,
    ParkingSlot,
    ParkingVoucher,
    Profile,
    ReportDailyUsage,
    RewardCatalogItem,
    RewardRedemption,
    RewardTransaction,
    SlotObservation,
    Vehicle,
    WrongParkingReport,
)
from src.models.schemas import ErrorCode, WrongParkingReason, WrongParkingReportStatus
from src.models.schemas import ParkingSlot as ParkingSlotSchema
from src.models.schemas import WrongParkingReport as WrongParkingReportSchema
from src.services import database as compatibility_database
from src.services import db_models as compatibility_models

EXPECTED_TABLES = {
    "agent_daily_usage",
    "report_daily_usage",
    "profiles",
    "parking_users",
    "vehicles",
    "map_nodes",
    "map_edges",
    "parking_slots",
    "parking_reservations",
    "parking_sessions",
    "parking_events",
    "idempotency_records",
    "wrong_parking_reports",
    "slot_observations",
    "reward_transactions",
    "reward_catalog_items",
    "reward_redemptions",
    "parking_vouchers",
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


def test_reward_redemption_models_keep_signed_ledger_and_voucher_guards():
    ledger = RewardTransaction.__table__
    catalog = RewardCatalogItem.__table__
    redemption = RewardRedemption.__table__
    voucher = ParkingVoucher.__table__

    assert "points_delta" in ledger.c
    assert "points" not in ledger.c
    assert {constraint.name for constraint in ledger.constraints} >= {
        "ck_reward_transactions_points_delta_nonzero",
        "uq_reward_transactions_source_transaction_type",
    }
    assert {constraint.name for constraint in catalog.constraints} >= {
        "ck_reward_catalog_items_free_minutes_range",
    }
    assert {constraint.name for constraint in redemption.constraints} >= {
        "ck_reward_redemptions_free_minutes_range",
    }
    assert {constraint.name for constraint in voucher.constraints} >= {
        "ck_parking_vouchers_free_minutes_range",
        "ck_parking_vouchers_expiry_after_issue",
    }
    assert "uq_parking_vouchers_applied_session" in {index.name for index in voucher.indexes}


def test_parking_migration_follows_profiles_revision():
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    parking_revision = scripts.get_revision("20260811_0002")

    location_cleanup_revision = scripts.get_revision("20260812_0003")
    nearest_aisle_revision = scripts.get_revision("20260813_0004")
    wrong_parking_report_revision = scripts.get_revision("20260815_0005")
    report_lifecycle_revision = scripts.get_revision("20260819_0006")
    contribution_revision = scripts.get_revision("0008")
    auth_report_merge_revision = scripts.get_revision("20260822_0009")
    integration_merge_revision = scripts.get_revision("20260824_0010")
    agent_quota_revision = scripts.get_revision("20260824_0011")
    report_quota_revision = scripts.get_revision("20260824_0012")
    verified_location_revision = scripts.get_revision("20260826_0013")
    idempotency_revision = scripts.get_revision("20260826_0014")
    invariant_revision = scripts.get_revision("20260826_0015")
    reward_revision = scripts.get_revision("20260830_0016")

    observation_evidence_revision = scripts.get_revision("20260831_0017")

    assert scripts.get_current_head() == "20260831_0017"
    assert parking_revision is not None
    assert parking_revision.down_revision == "20260804_0001"
    assert location_cleanup_revision is not None
    assert location_cleanup_revision.down_revision == "20260811_0002"
    assert nearest_aisle_revision is not None
    assert nearest_aisle_revision.down_revision == "20260812_0003"
    assert wrong_parking_report_revision is not None
    assert wrong_parking_report_revision.down_revision == "20260813_0004"
    assert report_lifecycle_revision is not None
    assert report_lifecycle_revision.down_revision == "20260815_0005"
    assert contribution_revision is not None
    assert contribution_revision.down_revision == "0007"
    assert auth_report_merge_revision is not None
    assert set(auth_report_merge_revision.down_revision) == {"0007", "20260821_0008"}
    assert integration_merge_revision is not None
    assert set(integration_merge_revision.down_revision) == {"0008", "20260822_0009"}
    assert agent_quota_revision is not None
    assert agent_quota_revision.down_revision == "20260824_0010"
    assert report_quota_revision is not None
    assert report_quota_revision.down_revision == "20260824_0011"
    assert verified_location_revision is not None
    assert verified_location_revision.down_revision == "20260824_0012"
    assert idempotency_revision is not None
    assert idempotency_revision.down_revision == "20260826_0013"
    assert invariant_revision is not None
    assert invariant_revision.down_revision == "20260826_0014"
    assert reward_revision is not None
    assert reward_revision.down_revision == "20260826_0015"
    assert observation_evidence_revision is not None
    assert observation_evidence_revision.down_revision == "20260830_0016"


def test_slot_observation_evidence_stores_only_private_metadata() -> None:
    observation = SlotObservation.__table__
    assert {"evidence_storage_path", "evidence_content_type", "evidence_size_bytes"} <= set(observation.c.keys())
    assert "ck_slot_observations_evidence_size_nonnegative" in {
        constraint.name for constraint in observation.constraints
    }


def test_agent_daily_usage_model_and_migration_constraints_match():
    table = AgentDailyUsage.__table__
    assert tuple(column.name for column in table.primary_key.columns) == (
        "user_id",
        "usage_date",
    )
    assert table.c.user_id.type.length == 64
    assert table.c.request_count.nullable is False
    assert table.c.created_at.type.timezone is True
    assert table.c.updated_at.type.timezone is True
    assert {constraint.name for constraint in table.constraints} >= {"ck_agent_daily_usage_request_count_nonnegative"}
    assert {index.name: tuple(column.name for column in index.columns) for index in table.indexes}[
        "ix_agent_daily_usage_usage_date"
    ] == ("usage_date",)
    assert {foreign_key.target_fullname for foreign_key in table.c.user_id.foreign_keys} == {"parking_users.id"}

    output = StringIO()
    config = Config("alembic.ini", output_buffer=output)
    config.attributes["configure_logger"] = False
    command.upgrade(config, "20260824_0010:20260824_0011", sql=True)
    migration_sql = output.getvalue()
    assert "CREATE TABLE agent_daily_usage" in migration_sql
    assert "PRIMARY KEY (user_id, usage_date)" in migration_sql
    assert "request_count >= 0" in migration_sql
    assert "FOREIGN KEY(user_id) REFERENCES parking_users (id) ON DELETE CASCADE" in migration_sql
    assert "CREATE INDEX ix_agent_daily_usage_usage_date" in migration_sql


def test_report_daily_usage_model_and_migration_constraints_match():
    table = ReportDailyUsage.__table__
    assert tuple(column.name for column in table.primary_key.columns) == (
        "user_id",
        "usage_date",
    )
    assert table.c.user_id.type.length == 64
    assert table.c.submission_count.nullable is False
    assert table.c.created_at.type.timezone is True
    assert table.c.updated_at.type.timezone is True
    assert {constraint.name for constraint in table.constraints} >= {
        "ck_report_daily_usage_submission_count_nonnegative"
    }
    assert {index.name: tuple(column.name for column in index.columns) for index in table.indexes}[
        "ix_report_daily_usage_usage_date"
    ] == ("usage_date",)
    user_foreign_key = next(iter(table.c.user_id.foreign_keys))
    assert user_foreign_key.target_fullname == "parking_users.id"
    assert user_foreign_key.ondelete == "CASCADE"

    output = StringIO()
    config = Config("alembic.ini", output_buffer=output)
    config.attributes["configure_logger"] = False
    command.upgrade(config, "20260824_0011:20260824_0012", sql=True)
    migration_sql = output.getvalue()
    assert "CREATE TABLE report_daily_usage" in migration_sql
    assert "PRIMARY KEY (user_id, usage_date)" in migration_sql
    assert "submission_count >= 0" in migration_sql
    assert "FOREIGN KEY(user_id) REFERENCES parking_users (id) ON DELETE CASCADE" in migration_sql
    assert "CREATE INDEX ix_report_daily_usage_usage_date" in migration_sql


def test_cold_start_sql_replaces_legacy_profile_enum_once():
    output = StringIO()
    config = Config("alembic.ini", output_buffer=output)
    config.attributes["configure_logger"] = False

    command.upgrade(config, "head", sql=True)

    migration_sql = output.getvalue()
    assert migration_sql.count("CREATE TYPE app_role_enum") == 2
    assert migration_sql.count("ALTER TYPE app_role_enum RENAME TO app_role_enum_legacy") == 1
    assert migration_sql.count("DROP TYPE app_role_enum_legacy") == 1


def test_report_lifecycle_migration_backfills_before_required_constraints():
    output = StringIO()
    config = Config("alembic.ini", output_buffer=output)
    config.attributes["configure_logger"] = False

    command.upgrade(config, "20260815_0005:20260819_0006", sql=True)

    migration_sql = output.getvalue()
    backfill_position = migration_sql.index("UPDATE wrong_parking_reports")
    assert "reason_code = 'OTHER'" in migration_sql
    assert "status = 'OPEN'" in migration_sql
    assert "version = 0" in migration_sql
    assert "updated_at = created_at" in migration_sql
    for column_name in ("reason_code", "status", "updated_at", "version"):
        not_null_position = migration_sql.index(f"ALTER COLUMN {column_name} SET NOT NULL")
        assert backfill_position < not_null_position


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
    slot_ids = {f"F1-{zone}{slot_number:02d}" for zone in "ABCD" for slot_number in range(1, 11)}
    node_ids = slot_ids | {f"F1-{zone}-{side}" for zone in "ABCD" for side in ("W", "E")}
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
    assert {(edge["from_node"], edge["to_node"]) for edge in inserted_edges} >= {
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


def test_vehicle_model_keeps_display_plate_and_sets_canonical_identity() -> None:
    vehicle = Vehicle(
        id="VEHICLE-PLATE",
        user_id="USER-001",
        plate_number=" 51a 12345 ",
        requires_charging=False,
    )

    assert vehicle.plate_number == "51A 12345"
    assert vehicle.normalized_plate_number == "51A12345"
    assert Vehicle.__table__.c.normalized_plate_number.unique is True
    assert Vehicle.__table__.c.plate_number.unique is not True


def test_map_slot_and_idempotency_constraints_match_hardened_contract() -> None:
    assert {constraint.name for constraint in MapNode.__table__.constraints} >= {"ck_map_nodes_id_matches_floor"}
    assert {constraint.name for constraint in ParkingSlot.__table__.constraints} >= {
        "ck_parking_slots_id_canonical",
        "ck_parking_slots_id_matches_floor",
        "ck_parking_slots_id_matches_zone",
    }
    assert tuple(column.name for column in IdempotencyRecord.__table__.primary_key.columns) == (
        "user_id",
        "operation",
        "key",
    )


def test_wrong_parking_report_lifecycle_model_has_required_contract_shape():
    table = WrongParkingReport.__table__

    assert table.c.description.nullable is True
    assert table.c.reason_code.nullable is False
    assert table.c.status.nullable is False
    assert table.c.updated_at.nullable is False
    assert table.c.version.nullable is False
    assert table.c.reason_code.type.name == "wrong_parking_reason_enum"
    assert table.c.status.type.name == "wrong_parking_report_status_enum"
    assert table.c.resolved_by.foreign_keys == set()
    assert {constraint.name for constraint in table.constraints} >= {"ck_wrong_parking_reports_version_nonnegative"}

    index_columns = {index.name: tuple(column.name for column in index.columns) for index in table.indexes}
    assert index_columns["ix_wrong_parking_reports_status_created"] == (
        "status",
        "created_at",
    )
    assert index_columns["ix_wrong_parking_reports_slot_status_created"] == (
        "slot_id",
        "status",
        "created_at",
    )


def test_wrong_parking_report_schema_exposes_lifecycle_and_rejects_negative_version():
    payload = {
        "id": "REPORT-001",
        "reporter_user_id": "USER-001",
        "slot_id": "F1-D01",
        "reason_code": WrongParkingReason.CROSSED_LINE,
        "status": WrongParkingReportStatus.OPEN,
        "description": None,
        "created_at": datetime(2026, 8, 19, 8, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 8, 19, 8, 0, tzinfo=UTC),
        "resolved_at": None,
        "resolved_by": None,
        "resolution_note": None,
        "version": 0,
    }

    report = WrongParkingReportSchema.model_validate(payload)

    assert report.reason_code is WrongParkingReason.CROSSED_LINE
    assert report.status is WrongParkingReportStatus.OPEN
    assert report.description is None
    with pytest.raises(ValidationError):
        WrongParkingReportSchema.model_validate({**payload, "version": -1})


def test_wrong_parking_report_enums_and_error_codes_are_stable():
    assert {reason.value for reason in WrongParkingReason} == {
        "WRONG_SLOT",
        "CROSSED_LINE",
        "BLOCKING_ACCESS",
        "OCCUPYING_CHARGER",
        "OTHER",
    }
    assert {status.value for status in WrongParkingReportStatus} == {
        "OPEN",
        "RESOLVED",
    }
    assert {
        ErrorCode.REPORT_NOT_FOUND.value,
        ErrorCode.REPORT_VERSION_CONFLICT.value,
        ErrorCode.INVALID_REPORT_TRANSITION.value,
    } == {
        "REPORT_NOT_FOUND",
        "REPORT_VERSION_CONFLICT",
        "INVALID_REPORT_TRANSITION",
    }
