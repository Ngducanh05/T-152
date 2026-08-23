import re
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
)

EntityId = Annotated[str, Field(min_length=1)]
FloorId = Literal["F1", "F2", "F3"]
FloorScopedId = Annotated[str, Field(pattern=r"^F[1-3]-", min_length=4)]
ZoneId = Literal["A", "B", "C", "D"]
FLOOR_IDS: tuple[str, ...] = ("F1", "F2", "F3")


class SlotStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    OCCUPIED = "OCCUPIED"


class ReservationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CONFIRMED = "CONFIRMED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ParkingSessionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class MapNodeType(StrEnum):
    ENTRANCE = "ENTRANCE"
    EXIT = "EXIT"
    CHECKPOINT = "CHECKPOINT"
    ELEVATOR = "ELEVATOR"
    RAMP = "RAMP"
    AISLE = "AISLE"
    SLOT = "SLOT"


class RouteMode(StrEnum):
    """Traversal mode used to filter mode-restricted edges before routing.

    Vehicles use ramps between floors; pedestrians use elevators. An edge whose
    ``allowed_mode`` is ``None`` is open to both modes.
    """

    VEHICLE = "VEHICLE"
    PEDESTRIAN = "PEDESTRIAN"


class ActorType(StrEnum):
    USER = "USER"
    ADMIN = "ADMIN"
    SIMULATOR = "SIMULATOR"
    CAMERA = "CAMERA"
    SYSTEM = "SYSTEM"


class ParkingEventType(StrEnum):
    VEHICLE_ENTERED = "VEHICLE_ENTERED"
    SLOT_RESERVED = "SLOT_RESERVED"
    RESERVATION_CANCELLED = "RESERVATION_CANCELLED"
    RESERVATION_EXPIRED = "RESERVATION_EXPIRED"
    VEHICLE_PARKED = "VEHICLE_PARKED"
    VEHICLE_LEFT_SLOT = "VEHICLE_LEFT_SLOT"
    VEHICLE_EXITED = "VEHICLE_EXITED"


class WrongParkingReportStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class SlotObservationStatus(StrEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class WrongParkingReportVerificationOutcome(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"
    UNVERIFIABLE = "UNVERIFIABLE"


class RewardSourceType(StrEnum):
    ADJACENT_SLOT_OBSERVATION = "ADJACENT_SLOT_OBSERVATION"
    WRONG_PARKING_REPORT = "WRONG_PARKING_REPORT"


class RewardTransactionType(StrEnum):
    CONTRIBUTION_REWARD = "CONTRIBUTION_REWARD"
    REWARD_REVERSAL = "REWARD_REVERSAL"
    ADMIN_ADJUSTMENT = "ADMIN_ADJUSTMENT"


class RewardTransactionStatus(StrEnum):
    PENDING = "PENDING"
    EARNED = "EARNED"
    CANCELLED = "CANCELLED"


class WrongParkingReason(StrEnum):
    WRONG_SLOT = "WRONG_SLOT"
    CROSSED_LINE = "CROSSED_LINE"
    BLOCKING_ACCESS = "BLOCKING_ACCESS"
    OCCUPYING_CHARGER = "OCCUPYING_CHARGER"
    OTHER = "OTHER"


class ChatUIActionType(StrEnum):
    SELECT_LOCATION = "SELECT_LOCATION"
    SELECT_PARKING_PREFERENCE = "SELECT_PARKING_PREFERENCE"
    SELECT_SLOT = "SELECT_SLOT"
    RESERVE_AND_ROUTE = "RESERVE_AND_ROUTE"
    CONFIRM_PARKING = "CONFIRM_PARKING"
    FIND_VEHICLE = "FIND_VEHICLE"
    COMPLETE_SESSION = "COMPLETE_SESSION"
    OPEN_WRONG_PARKING_REPORT = "OPEN_WRONG_PARKING_REPORT"
    CANCEL = "CANCEL"


class ChatUIActionStyle(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    DANGER = "danger"


class ErrorCode(StrEnum):
    INVALID_TRANSITION = "INVALID_TRANSITION"
    SLOT_NOT_FOUND = "SLOT_NOT_FOUND"
    ROUTE_NODE_NOT_FOUND = "ROUTE_NODE_NOT_FOUND"
    ROUTE_NOT_FOUND = "ROUTE_NOT_FOUND"
    ACTIVE_SESSION_NOT_FOUND = "ACTIVE_SESSION_NOT_FOUND"
    SLOT_NOT_AVAILABLE = "SLOT_NOT_AVAILABLE"
    ACTIVE_RESERVATION_EXISTS = "ACTIVE_RESERVATION_EXISTS"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    VEHICLE_NOT_FOUND = "VEHICLE_NOT_FOUND"
    RESERVATION_NOT_FOUND = "RESERVATION_NOT_FOUND"
    ACTIVE_RESERVATION_NOT_FOUND = "ACTIVE_RESERVATION_NOT_FOUND"
    RESERVATION_EXPIRED = "RESERVATION_EXPIRED"
    ACTIVE_SESSION_EXISTS = "ACTIVE_SESSION_EXISTS"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    LOCATION_NODE_NOT_FOUND = "LOCATION_NODE_NOT_FOUND"
    CURRENT_LOCATION_NOT_FOUND = "CURRENT_LOCATION_NOT_FOUND"
    INVALID_LOCATION_NODE_TYPE = "INVALID_LOCATION_NODE_TYPE"
    REPORT_NOT_FOUND = "REPORT_NOT_FOUND"
    REPORT_VERSION_CONFLICT = "REPORT_VERSION_CONFLICT"
    INVALID_REPORT_TRANSITION = "INVALID_REPORT_TRANSITION"
    REPORT_EVIDENCE_INVALID = "REPORT_EVIDENCE_INVALID"
    OBSERVATION_NOT_FOUND = "OBSERVATION_NOT_FOUND"
    OBSERVATION_ALREADY_EXISTS = "OBSERVATION_ALREADY_EXISTS"
    OBSERVATION_EXPIRED = "OBSERVATION_EXPIRED"
    INVALID_OBSERVATION_TRANSITION = "INVALID_OBSERVATION_TRANSITION"
    OBSERVATION_VERSION_CONFLICT = "OBSERVATION_VERSION_CONFLICT"
    REWARD_ALREADY_SETTLED = "REWARD_ALREADY_SETTLED"
    CONTRIBUTION_DAILY_LIMIT_REACHED = "CONTRIBUTION_DAILY_LIMIT_REACHED"
    REPORT_REWARD_DUPLICATE = "REPORT_REWARD_DUPLICATE"
    AGENT_TOOL_UNAVAILABLE = "AGENT_TOOL_UNAVAILABLE"
    SPEECH_AUDIO_INVALID = "SPEECH_AUDIO_INVALID"
    SPEECH_AUDIO_TOO_LARGE = "SPEECH_AUDIO_TOO_LARGE"
    SPEECH_NO_TRANSCRIPT = "SPEECH_NO_TRANSCRIPT"
    SPEECH_TRANSCRIPTION_TIMEOUT = "SPEECH_TRANSCRIPTION_TIMEOUT"
    SPEECH_TRANSCRIPTION_UNAVAILABLE = "SPEECH_TRANSCRIPTION_UNAVAILABLE"


class ContractModel(BaseModel):
    """Base configuration shared by API contract models."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def timestamps_must_be_utc(cls, value: object) -> object:
        if isinstance(value, datetime) and value.utcoffset() != timedelta(0):
            raise ValueError("timestamps must use UTC")
        return value


class User(ContractModel):
    id: EntityId
    display_name: str
    current_node_id: FloorScopedId | None = None


class Vehicle(ContractModel):
    id: EntityId
    user_id: EntityId
    plate_number: str
    requires_charging: bool = False


class ParkingSlot(ContractModel):
    id: FloorScopedId
    floor_id: FloorId
    zone_id: ZoneId
    node_id: FloorScopedId
    status: SlotStatus
    has_charger: bool
    is_accessible: bool
    version: int = Field(ge=0)
    occupied_by_vehicle_id: EntityId | None = None


class ParkingReservation(ContractModel):
    id: EntityId
    user_id: EntityId
    vehicle_id: EntityId
    slot_id: FloorScopedId
    status: ReservationStatus
    expires_at: AwareDatetime
    created_at: AwareDatetime


class ParkingSession(ContractModel):
    id: EntityId
    user_id: EntityId
    vehicle_id: EntityId
    slot_id: FloorScopedId
    status: ParkingSessionStatus
    parked_at: AwareDatetime
    completed_at: AwareDatetime | None = None


class MapNode(ContractModel):
    id: FloorScopedId
    floor_id: FloorId
    type: MapNodeType
    x: float
    y: float


class MapEdge(ContractModel):
    from_node: FloorScopedId
    to_node: FloorScopedId
    distance_m: float = Field(gt=0)
    bidirectional: bool = True
    enabled: bool = True
    allowed_mode: RouteMode | None = Field(
        default=None,
        description="Restrict traversal to one mode; null keeps the edge open to both.",
    )


class RouteResult(ContractModel):
    path: list[FloorScopedId]
    distance_m: float = Field(ge=0)
    polyline: list[tuple[float, float]]


class RecommendationRequest(ContractModel):
    user_id: EntityId
    start_node_id: FloorScopedId
    floor_id: FloorId | None = Field(
        default=None,
        description="Restrict candidates to one floor; null ranks every floor by real route distance.",
    )
    zone_id: ZoneId | None = None
    charging_required: bool = False
    accessible_required: bool = False
    near_elevator: bool = False
    limit: int = Field(default=3, gt=0)


class RecommendationCandidate(ContractModel):
    slot_id: FloorScopedId
    score: float = Field(ge=0, le=100)
    distance_m: float = Field(ge=0)
    reasons: list[str]

    @field_serializer("score", when_used="json")
    def serialize_score(self, score: float) -> float:
        return round(score, 2)


class RecommendationResult(ContractModel):
    recommendations: list[RecommendationCandidate]
    parking_state_version: int = Field(ge=0)


class ParkingEvent(ContractModel):
    id: EntityId
    event_type: ParkingEventType
    slot_id: FloorScopedId | None = None
    actor_type: ActorType
    actor_id: EntityId | None = None
    old_status: SlotStatus | None = None
    new_status: SlotStatus | None = None
    created_at: AwareDatetime
    metadata: dict[str, object] = Field(default_factory=dict)


class SlotObservation(ContractModel):
    id: EntityId
    observer_user_id: EntityId
    observer_session_id: EntityId
    slot_id: FloorScopedId
    observed_status: Literal[SlotStatus.AVAILABLE, SlotStatus.OCCUPIED]
    verification_status: SlotObservationStatus
    reward_points: int = Field(ge=0)
    observed_slot_version: int = Field(ge=0)
    created_at: AwareDatetime
    expires_at: AwareDatetime
    verified_at: AwareDatetime | None = None
    verified_by: EntityId | None = None
    rejection_reason: str | None = Field(default=None, max_length=500)
    version: int = Field(ge=0)
    reward_status: RewardTransactionStatus | None = None


class WrongParkingReport(ContractModel):
    id: EntityId
    reporter_user_id: EntityId
    slot_id: FloorScopedId
    reason_code: WrongParkingReason
    status: WrongParkingReportStatus
    observed_plate_number: str | None = None
    description: str | None = None
    evidence_storage_path: str | None = None
    evidence_content_type: str | None = None
    evidence_size_bytes: int | None = Field(default=None, ge=0)
    created_at: AwareDatetime
    updated_at: AwareDatetime
    resolved_at: AwareDatetime | None = None
    resolved_by: EntityId | None = None
    resolution_note: str | None = None
    verification_outcome: WrongParkingReportVerificationOutcome = (
        WrongParkingReportVerificationOutcome.PENDING
    )
    reward_points: int = Field(default=0, ge=0)
    reward_status: RewardTransactionStatus | None = None
    duplicate_candidate_of_id: EntityId | None = None
    version: int = Field(ge=0)


class RewardTransaction(ContractModel):
    id: EntityId
    user_id: EntityId
    source_type: RewardSourceType
    source_reference: EntityId
    transaction_type: RewardTransactionType
    status: RewardTransactionStatus
    points: int = Field(ge=0)
    created_at: AwareDatetime
    settled_at: AwareDatetime | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class RewardSummary(ContractModel):
    available_points: int = Field(ge=0)
    pending_points: int = Field(ge=0)
    verified_contributions: int = Field(ge=0)
    daily_pending_points: int = Field(ge=0)
    daily_earned_points: int = Field(ge=0)
    daily_limit_points: int = Field(ge=0)


class RewardConfiguration(ContractModel):
    adjacent_observation_reward_points: int = Field(ge=0)
    wrong_parking_report_reward_points: int = Field(ge=0)
    contribution_daily_points_limit: int = Field(ge=0)


class ContributionRecord(ContractModel):
    id: EntityId
    source_type: RewardSourceType
    source_reference: EntityId
    observer_session_id: EntityId | None = None
    floor_id: FloorId
    slot_id: FloorScopedId
    points: int = Field(ge=0)
    status: RewardTransactionStatus | None = None
    created_at: AwareDatetime
    settled_at: AwareDatetime | None = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_id: str = Field(min_length=1, max_length=128)
    user_id: EntityId
    vehicle_id: EntityId | None = None
    current_location: FloorScopedId | None = None
    message: str = Field(min_length=1, max_length=5000, description="Tin nhắn từ user")

    @field_validator("thread_id", "message")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class ChatUIAction(ContractModel):
    id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9:-]+$")
    type: ChatUIActionType
    label: str = Field(min_length=1, max_length=100)
    payload: dict[str, str] = Field(default_factory=dict)
    style: ChatUIActionStyle = ChatUIActionStyle.SECONDARY
    requires_confirmation: bool = False

    @field_validator("payload")
    @classmethod
    def payload_uses_allowlisted_fields(cls, value: dict[str, str]) -> dict[str, str]:
        allowed_fields = {"node_id", "slot_id", "preference"}
        unknown_fields = set(value) - allowed_fields
        if unknown_fields:
            raise ValueError("ui action payload contains unsupported fields")
        allowed_preferences = {"ANY", "EV", "ACCESSIBLE", "NEAR_ELEVATOR"}
        preference = value.get("preference")
        if preference is not None and preference not in allowed_preferences:
            raise ValueError("ui action preference is not supported")
        slot_id = value.get("slot_id")
        if slot_id is not None and re.fullmatch(
            r"^F[1-3]-[A-D](?:0[1-9]|10)$", slot_id
        ) is None:
            raise ValueError("ui action slot_id is not canonical")
        node_id = value.get("node_id")
        if node_id is not None and re.fullmatch(r"^F[1-3]-[A-Z0-9-]+$", node_id) is None:
            raise ValueError("ui action node_id is not canonical")
        return value


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_id: str
    message: str = Field(description="Phản hồi công khai từ agent")
    intent: str | None = None
    selected_slot: str | None = None
    tool_names: list[str] = Field(default_factory=list)
    current_location: FloorScopedId | None = None
    recommended_slot_ids: list[FloorScopedId] = Field(default_factory=list)
    route: RouteResult | None = None
    ui_actions: list[ChatUIAction] = Field(default_factory=list, max_length=5)


class SpeechTranscriptionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=5000)
