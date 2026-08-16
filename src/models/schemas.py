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
FloorId = Literal["F1"]
FloorScopedId = Annotated[str, Field(pattern=r"^F1-", min_length=4)]
ZoneId = Literal["A", "B", "C", "D"]


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
    AISLE = "AISLE"
    SLOT = "SLOT"


class ActorType(StrEnum):
    USER = "USER"
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


class RouteResult(ContractModel):
    path: list[FloorScopedId]
    distance_m: float = Field(ge=0)
    polyline: list[tuple[float, float]]


class RecommendationRequest(ContractModel):
    user_id: EntityId
    start_node_id: FloorScopedId
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


class WrongParkingReport(ContractModel):
    id: EntityId
    reporter_user_id: EntityId
    slot_id: FloorScopedId
    observed_plate_number: str | None = None
    description: str
    created_at: AwareDatetime


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


class SpeechTranscriptionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=5000)
