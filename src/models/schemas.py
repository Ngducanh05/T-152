from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

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
    INVALID_QR_PAYLOAD = "INVALID_QR_PAYLOAD"
    AGENT_TOOL_UNAVAILABLE = "AGENT_TOOL_UNAVAILABLE"


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


class LocationCheckpoint(ContractModel):
    id: FloorScopedId
    node_id: FloorScopedId
    qr_payload: str


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


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000, description="Tin nhắn từ user")


class ChatResponse(BaseModel):
    response: str = Field(..., description="Phản hồi từ agent")
    analysis: str = Field(default="", description="Phân tích nội bộ")
