"""Safe LangGraph tool adapters over deterministic ParkSmart Core Services.

Identity and database dependencies come exclusively from ``AgentToolRuntime``.
These adapters do not contain parking rules, issue ORM queries, or call internal HTTP.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from langchain_core.tools import BaseTool, tool
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.tools.common import (
    AgentToolError,
    AgentToolRuntime,
    ToolResult,
    execute_tool,
    require_vehicle_id,
    tool_error,
    tool_success,
)
from src.core.location import LocationService
from src.core.parking_session import ParkedVehicle, ParkingSessionService
from src.core.parking_state import ParkingStateService, ParkingStatus
from src.core.recommendation import RecommendationService
from src.core.reservation import ReservationService
from src.core.routing import RoutingService
from src.models.schemas import (
    ErrorCode,
    FloorId,
    FloorScopedId,
    ParkingReservation,
    ParkingSession,
    ParkingSlot,
    RecommendationRequest,
    ReservationStatus,
    RouteResult,
    ZoneId,
)

ExpectedVersion = Annotated[int | None, Field(ge=0)]
RecommendationLimit = Annotated[int, Field(gt=0, le=10)]


def _parking_status_data(status: ParkingStatus) -> dict[str, object]:
    return {
        "total": status.total,
        "available": status.available,
        "reserved": status.reserved,
        "occupied": status.occupied,
        "by_zone": {
            zone_id: {slot_status.value: count for slot_status, count in counts.items()}
            for zone_id, counts in status.by_zone.items()
        },
    }


def _reservation_data(reservation: object) -> dict[str, object]:
    return ParkingReservation.model_validate(
        reservation,
        from_attributes=True,
    ).model_dump(mode="json")


def _slot_data(slot: object) -> dict[str, object]:
    return ParkingSlot.model_validate(slot, from_attributes=True).model_dump(mode="json")


def _session_data(parking_session: object) -> dict[str, object]:
    return ParkingSession.model_validate(
        parking_session,
        from_attributes=True,
    ).model_dump(mode="json")


def _route_data(
    route: RouteResult,
    *,
    start_node_id: str,
    destination_node_id: str,
) -> dict[str, object]:
    return {
        "start_node_id": start_node_id,
        "destination_node_id": destination_node_id,
        **route.model_dump(mode="json"),
    }


async def _confirmed_location(session: AsyncSession, user_id: str) -> str:
    node_id = await LocationService(session).get_current_location(user_id)
    if node_id is None:
        raise AgentToolError(
            ErrorCode.CURRENT_LOCATION_NOT_FOUND,
            "Please confirm your current location first.",
        )
    return node_id


@tool
async def get_parking_status(runtime: AgentToolRuntime) -> ToolResult:
    """Get the current counts of available, reserved, and occupied parking slots."""

    async def operation(session: AsyncSession) -> ToolResult:
        status = await ParkingStateService(session).get_parking_status()
        return tool_success(_parking_status_data(status))

    return await execute_tool(runtime, "get_parking_status", operation)


@tool
async def get_parking_slot_status(
    slot_id: FloorScopedId,
    *,
    runtime: AgentToolRuntime,
) -> ToolResult:
    """Get the authoritative status and capabilities of one exact parking slot."""

    async def operation(session: AsyncSession) -> ToolResult:
        slot = await ParkingStateService(session).get_slot(slot_id)
        return tool_success(_slot_data(slot))

    return await execute_tool(runtime, "get_parking_slot_status", operation)


@tool
async def recommend_parking_slot(
    floor_id: FloorId | None = None,
    zone_id: ZoneId | None = None,
    charging_required: bool = False,
    accessible_required: bool = False,
    near_elevator: bool = False,
    limit: RecommendationLimit = 3,
    *,
    runtime: AgentToolRuntime,
) -> ToolResult:
    """Recommend available slots from confirmed location without reserving one."""

    async def operation(session: AsyncSession) -> ToolResult:
        start_node_id = await _confirmed_location(session, runtime.context.user_id)
        request = RecommendationRequest(
            user_id=runtime.context.user_id,
            start_node_id=start_node_id,
            floor_id=floor_id,
            zone_id=zone_id,
            charging_required=charging_required,
            accessible_required=accessible_required,
            near_elevator=near_elevator,
            limit=limit,
        )
        result = await RecommendationService(
            session,
            ParkingStateService(session),
            RoutingService(session),
        ).recommend(request)
        return tool_success(result.model_dump(mode="json"))

    return await execute_tool(runtime, "recommend_parking_slot", operation, write=True)


@tool
async def reserve_parking_slot(
    slot_id: FloorScopedId,
    expected_version: ExpectedVersion = None,
    *,
    runtime: AgentToolRuntime,
) -> ToolResult:
    """Reserve a slot only after the user explicitly accepts that exact slot."""

    async def operation(session: AsyncSession) -> ToolResult:
        vehicle_id = require_vehicle_id(runtime)
        reservation = await ReservationService(
            session,
            ParkingStateService(session),
        ).create_reservation(
            runtime.context.user_id,
            vehicle_id,
            slot_id,
            expected_version=expected_version,
        )
        return tool_success(_reservation_data(reservation))

    return await execute_tool(runtime, "reserve_parking_slot", operation, write=True)


@tool
async def get_route(
    destination_node_id: FloorScopedId,
    *,
    runtime: AgentToolRuntime,
) -> ToolResult:
    """Get a route from the user's confirmed location to a destination node."""

    async def operation(session: AsyncSession) -> ToolResult:
        start_node_id = await _confirmed_location(session, runtime.context.user_id)
        route = await RoutingService(session).get_route(
            start_node_id,
            destination_node_id,
        )
        return tool_success(
            _route_data(
                route,
                start_node_id=start_node_id,
                destination_node_id=destination_node_id,
            )
        )

    return await execute_tool(runtime, "get_route", operation)


@tool
async def set_user_location(
    node_id: FloorScopedId,
    *,
    runtime: AgentToolRuntime,
) -> ToolResult:
    """Confirm the user's current canonical map node by its ID."""

    async def operation(session: AsyncSession) -> ToolResult:
        confirmed_node_id = await LocationService(session).confirm_location(
            runtime.context.user_id,
            node_id,
        )
        return tool_success(
            {"user_id": runtime.context.user_id, "node_id": confirmed_node_id}
        )

    return await execute_tool(runtime, "set_user_location", operation, write=True)


@tool
async def confirm_parking(
    reservation_id: str,
    expected_version: ExpectedVersion = None,
    *,
    runtime: AgentToolRuntime,
) -> ToolResult:
    """Confirm parking for the trusted user and vehicle reservation."""

    async def operation(session: AsyncSession) -> ToolResult:
        vehicle_id = require_vehicle_id(runtime)
        current_time = datetime.now(UTC)
        state_service = ParkingStateService(session)
        reservation_service = ReservationService(session, state_service)
        reservation = await reservation_service.get_reservation(reservation_id)
        expired = reservation.status is ReservationStatus.EXPIRED
        if not expired:
            expired = await reservation_service.expire_reservation_if_needed(
                reservation,
                now=current_time,
            )
        if expired:
            return tool_error(
                ErrorCode.RESERVATION_EXPIRED,
                "Reservation has expired.",
            )

        parking_session = await ParkingSessionService(
            session,
            state_service,
            clock=lambda: current_time,
        ).confirm_parking(
            runtime.context.user_id,
            vehicle_id,
            reservation_id,
            expected_version=expected_version,
        )
        return tool_success(_session_data(parking_session))

    return await execute_tool(runtime, "confirm_parking", operation, write=True)


@tool
async def find_parked_vehicle(runtime: AgentToolRuntime) -> ToolResult:
    """Find the vehicle using only the trusted user's active parking session."""

    async def operation(session: AsyncSession) -> ToolResult:
        vehicle: ParkedVehicle = await ParkingSessionService(
            session
        ).find_parked_vehicle(runtime.context.user_id)
        return tool_success(
            {
                "session_id": vehicle.session_id,
                "vehicle_id": vehicle.vehicle_id,
                "slot_id": vehicle.slot_id,
                "destination_node_id": vehicle.destination_node_id,
            }
        )

    return await execute_tool(runtime, "find_parked_vehicle", operation)


@tool
async def cancel_reservation(
    reservation_id: str,
    *,
    runtime: AgentToolRuntime,
) -> ToolResult:
    """Cancel a reservation owned by the trusted user identity."""

    async def operation(session: AsyncSession) -> ToolResult:
        service = ReservationService(session, ParkingStateService(session))
        reservation = await service.get_reservation(reservation_id)
        if reservation.status is not ReservationStatus.EXPIRED:
            reservation = await service.cancel_reservation(
                reservation_id,
                user_id=runtime.context.user_id,
            )
        if reservation.status is ReservationStatus.EXPIRED:
            return tool_error(
                ErrorCode.RESERVATION_EXPIRED,
                "Reservation has expired.",
            )
        return tool_success(_reservation_data(reservation))

    return await execute_tool(runtime, "cancel_reservation", operation, write=True)


@tool
async def complete_parking_session(
    session_id: str,
    expected_version: ExpectedVersion = None,
    *,
    runtime: AgentToolRuntime,
) -> ToolResult:
    """Complete a parking session owned by the trusted user identity."""

    async def operation(session: AsyncSession) -> ToolResult:
        parking_session = await ParkingSessionService(
            session,
            ParkingStateService(session),
        ).complete_session(
            session_id,
            user_id=runtime.context.user_id,
            expected_version=expected_version,
        )
        return tool_success(_session_data(parking_session))

    return await execute_tool(
        runtime,
        "complete_parking_session",
        operation,
        write=True,
    )


PARKING_TOOLS: tuple[BaseTool, ...] = (
    get_parking_status,
    get_parking_slot_status,
    recommend_parking_slot,
    reserve_parking_slot,
    get_route,
    set_user_location,
    confirm_parking,
    find_parked_vehicle,
    cancel_reservation,
    complete_parking_session,
)

__all__ = [
    "PARKING_TOOLS",
    "cancel_reservation",
    "complete_parking_session",
    "confirm_parking",
    "find_parked_vehicle",
    "get_parking_status",
    "get_parking_slot_status",
    "get_route",
    "recommend_parking_slot",
    "reserve_parking_slot",
    "set_user_location",
]
