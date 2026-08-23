import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.models.schemas import (
    ActorType,
    MapNodeType,
    ParkingEventType,
    ParkingSessionStatus,
    ReservationStatus,
    RewardSourceType,
    RewardTransactionStatus,
    RewardTransactionType,
    RouteMode,
    SlotObservationStatus,
    SlotStatus,
    WrongParkingReason,
    WrongParkingReportStatus,
    WrongParkingReportVerificationOutcome,
)


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [item.value for item in enum_class]


class Base(DeclarativeBase):
    """The only declarative base used by ParkSmart persistence models."""


class AppRoleEnum(StrEnum):
    RESIDENT = "resident"
    SECURITY = "security"
    ADMIN = "admin"


class Profile(Base):
    """Existing profile linked one-to-one with a Supabase Auth user."""

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    app_role: Mapped[AppRoleEnum] = mapped_column(
        Enum(AppRoleEnum, name="app_role_enum", values_callable=_enum_values),
        nullable=False,
        default=AppRoleEnum.RESIDENT,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class MapNode(Base):
    __tablename__ = "map_nodes"
    __table_args__ = (
        CheckConstraint("id ~ '^F[1-3]-'", name="ck_map_nodes_id_floor_prefix"),
        CheckConstraint("floor_id IN ('F1', 'F2', 'F3')", name="ck_map_nodes_floor"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    floor_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    type: Mapped[MapNodeType] = mapped_column(
        Enum(MapNodeType, name="map_node_type_enum", values_callable=_enum_values),
        nullable=False,
        index=True,
    )
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)


class ParkingUser(Base):
    __tablename__ = "parking_users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    current_node_id: Mapped[str | None] = mapped_column(
        ForeignKey("map_nodes.id", ondelete="SET NULL"), nullable=True, index=True
    )


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("parking_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plate_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    requires_charging: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class MapEdge(Base):
    __tablename__ = "map_edges"
    __table_args__ = (
        CheckConstraint("from_node <> to_node", name="ck_map_edges_distinct_nodes"),
        CheckConstraint("distance_m > 0", name="ck_map_edges_positive_distance"),
        Index("ix_map_edges_to_node", "to_node"),
    )

    from_node: Mapped[str] = mapped_column(
        ForeignKey("map_nodes.id", ondelete="CASCADE"), primary_key=True
    )
    to_node: Mapped[str] = mapped_column(
        ForeignKey("map_nodes.id", ondelete="CASCADE"), primary_key=True
    )
    distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    bidirectional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    allowed_mode: Mapped[RouteMode | None] = mapped_column(
        Enum(RouteMode, name="route_mode_enum", values_callable=_enum_values),
        nullable=True,
    )


class ParkingSlot(Base):
    __tablename__ = "parking_slots"
    __table_args__ = (
        CheckConstraint("id ~ '^F[1-3]-'", name="ck_parking_slots_id_floor_prefix"),
        CheckConstraint("floor_id IN ('F1', 'F2', 'F3')", name="ck_parking_slots_floor"),
        CheckConstraint("zone_id IN ('A', 'B', 'C', 'D')", name="ck_parking_slots_zone"),
        CheckConstraint("version >= 0", name="ck_parking_slots_version_nonnegative"),
        Index("ix_parking_slots_status_zone", "status", "zone_id"),
        Index("ix_parking_slots_floor_status", "floor_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    floor_id: Mapped[str] = mapped_column(String(16), nullable=False)
    zone_id: Mapped[str] = mapped_column(String(16), nullable=False)
    node_id: Mapped[str] = mapped_column(
        ForeignKey("map_nodes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[SlotStatus] = mapped_column(
        Enum(SlotStatus, name="slot_status_enum", values_callable=_enum_values),
        nullable=False,
        default=SlotStatus.AVAILABLE,
        server_default=text("'AVAILABLE'"),
    )
    has_charger: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_accessible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    occupied_by_vehicle_id: Mapped[str | None] = mapped_column(
        ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True, index=True
    )


class ParkingReservation(Base):
    __tablename__ = "parking_reservations"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="ck_reservations_expiry_after_creation"),
        Index(
            "uq_parking_reservations_active_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index(
            "uq_parking_reservations_active_vehicle",
            "vehicle_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index(
            "uq_parking_reservations_active_slot",
            "slot_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("parking_users.id", ondelete="RESTRICT"), nullable=False
    )
    vehicle_id: Mapped[str] = mapped_column(
        ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False
    )
    slot_id: Mapped[str] = mapped_column(
        ForeignKey("parking_slots.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus, name="reservation_status_enum", values_callable=_enum_values),
        nullable=False,
        default=ReservationStatus.ACTIVE,
        server_default=text("'ACTIVE'"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ParkingSession(Base):
    __tablename__ = "parking_sessions"
    __table_args__ = (
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= parked_at",
            name="ck_sessions_completed_after_parked",
        ),
        Index(
            "uq_parking_sessions_active_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index(
            "uq_parking_sessions_active_vehicle",
            "vehicle_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index(
            "uq_parking_sessions_active_slot",
            "slot_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("parking_users.id", ondelete="RESTRICT"), nullable=False
    )
    vehicle_id: Mapped[str] = mapped_column(
        ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False
    )
    slot_id: Mapped[str] = mapped_column(
        ForeignKey("parking_slots.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[ParkingSessionStatus] = mapped_column(
        Enum(
            ParkingSessionStatus,
            name="parking_session_status_enum",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=ParkingSessionStatus.ACTIVE,
        server_default=text("'ACTIVE'"),
    )
    parked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ParkingEvent(Base):
    __tablename__ = "parking_events"
    __table_args__ = (Index("ix_parking_events_slot_created", "slot_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[ParkingEventType] = mapped_column(
        Enum(ParkingEventType, name="parking_event_type_enum", values_callable=_enum_values),
        nullable=False,
        index=True,
    )
    slot_id: Mapped[str | None] = mapped_column(
        ForeignKey("parking_slots.id", ondelete="SET NULL"), nullable=True
    )
    actor_type: Mapped[ActorType] = mapped_column(
        Enum(ActorType, name="actor_type_enum", values_callable=_enum_values), nullable=False
    )
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    old_status: Mapped[SlotStatus | None] = mapped_column(
        Enum(SlotStatus, name="slot_status_enum", values_callable=_enum_values), nullable=True
    )
    new_status: Mapped[SlotStatus | None] = mapped_column(
        Enum(SlotStatus, name="slot_status_enum", values_callable=_enum_values), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    event_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class SlotObservation(Base):
    __tablename__ = "slot_observations"
    __table_args__ = (
        CheckConstraint("reward_points >= 0", name="ck_slot_observations_reward_nonnegative"),
        CheckConstraint("version >= 0", name="ck_slot_observations_version_nonnegative"),
        CheckConstraint(
            "observed_slot_version >= 0",
            name="ck_slot_observations_slot_version_nonnegative",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_slot_observations_expiry_after_creation",
        ),
        UniqueConstraint(
            "observer_session_id",
            "slot_id",
            name="uq_slot_observations_session_slot",
        ),
        Index(
            "ix_slot_observations_verification_created",
            "verification_status",
            "created_at",
        ),
        Index("ix_slot_observations_slot_created", "slot_id", "created_at"),
        Index("ix_slot_observations_user_created", "observer_user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    observer_user_id: Mapped[str] = mapped_column(
        ForeignKey("parking_users.id", ondelete="RESTRICT"), nullable=False
    )
    observer_session_id: Mapped[str] = mapped_column(
        ForeignKey("parking_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    slot_id: Mapped[str] = mapped_column(
        ForeignKey("parking_slots.id", ondelete="RESTRICT"), nullable=False
    )
    observed_status: Mapped[SlotStatus] = mapped_column(
        Enum(SlotStatus, name="slot_status_enum", values_callable=_enum_values),
        nullable=False,
    )
    verification_status: Mapped[SlotObservationStatus] = mapped_column(
        Enum(
            SlotObservationStatus,
            name="slot_observation_status_enum",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=SlotObservationStatus.PENDING,
        server_default=text("'PENDING'"),
    )
    reward_points: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    observed_slot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )


class RewardTransaction(Base):
    __tablename__ = "reward_transactions"
    __table_args__ = (
        CheckConstraint("points >= 0", name="ck_reward_transactions_points_nonnegative"),
        UniqueConstraint(
            "source_type",
            "source_reference",
            name="uq_reward_transactions_source",
        ),
        Index(
            "ix_reward_transactions_user_status_created",
            "user_id",
            "status",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("parking_users.id", ondelete="RESTRICT"), nullable=False
    )
    source_type: Mapped[RewardSourceType] = mapped_column(
        Enum(RewardSourceType, name="reward_source_type_enum", values_callable=_enum_values),
        nullable=False,
    )
    source_reference: Mapped[str] = mapped_column(String(64), nullable=False)
    transaction_type: Mapped[RewardTransactionType] = mapped_column(
        Enum(
            RewardTransactionType,
            name="reward_transaction_type_enum",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=RewardTransactionType.CONTRIBUTION_REWARD,
        server_default=text("'CONTRIBUTION_REWARD'"),
    )
    status: Mapped[RewardTransactionStatus] = mapped_column(
        Enum(
            RewardTransactionStatus,
            name="reward_transaction_status_enum",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=RewardTransactionStatus.PENDING,
        server_default=text("'PENDING'"),
    )
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transaction_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class WrongParkingReport(Base):
    __tablename__ = "wrong_parking_reports"
    __table_args__ = (
        CheckConstraint(
            "version >= 0",
            name="ck_wrong_parking_reports_version_nonnegative",
        ),
        CheckConstraint(
            "reward_points >= 0",
            name="ck_wrong_parking_reports_reward_nonnegative",
        ),
        Index("ix_wrong_parking_reports_created", "created_at"),
        Index("ix_wrong_parking_reports_slot_created", "slot_id", "created_at"),
        Index("ix_wrong_parking_reports_status_created", "status", "created_at"),
        Index(
            "ix_wrong_parking_reports_slot_status_created",
            "slot_id",
            "status",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    reporter_user_id: Mapped[str] = mapped_column(
        ForeignKey("parking_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    slot_id: Mapped[str] = mapped_column(
        ForeignKey("parking_slots.id", ondelete="RESTRICT"), nullable=False
    )
    reason_code: Mapped[WrongParkingReason] = mapped_column(
        Enum(
            WrongParkingReason,
            name="wrong_parking_reason_enum",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=WrongParkingReason.OTHER,
        server_default=text("'OTHER'"),
    )
    status: Mapped[WrongParkingReportStatus] = mapped_column(
        Enum(
            WrongParkingReportStatus,
            name="wrong_parking_report_status_enum",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=WrongParkingReportStatus.OPEN,
        server_default=text("'OPEN'"),
    )
    observed_plate_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verification_outcome: Mapped[WrongParkingReportVerificationOutcome] = mapped_column(
        Enum(
            WrongParkingReportVerificationOutcome,
            name="wrong_parking_report_verification_outcome_enum",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=WrongParkingReportVerificationOutcome.PENDING,
        server_default=text("'PENDING'"),
    )
    reward_points: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    duplicate_candidate_of_id: Mapped[str | None] = mapped_column(
        ForeignKey("wrong_parking_reports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )


__all__ = [
    "ActorType",
    "AppRoleEnum",
    "Base",
    "MapEdge",
    "MapNode",
    "ParkingEvent",
    "ParkingEventType",
    "ParkingReservation",
    "ParkingSession",
    "ParkingSessionStatus",
    "ParkingSlot",
    "ParkingUser",
    "Profile",
    "ReservationStatus",
    "RewardSourceType",
    "RewardTransaction",
    "RewardTransactionStatus",
    "RewardTransactionType",
    "RouteMode",
    "SlotObservation",
    "SlotObservationStatus",
    "SlotStatus",
    "Vehicle",
    "WrongParkingReason",
    "WrongParkingReport",
    "WrongParkingReportStatus",
    "WrongParkingReportVerificationOutcome",
]
