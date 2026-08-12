from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolRuntime

from src.agents.context import AgentRuntimeContext
from src.agents.tools.parking import (
    PARKING_TOOLS,
    cancel_reservation,
    complete_parking_session,
    confirm_parking,
    find_parked_vehicle,
    get_parking_status,
    get_route,
    recommend_parking_slot,
    reserve_parking_slot,
    set_user_location,
)
from src.core.parking_session import ParkedVehicle, ParkingSessionService
from src.core.parking_state import ParkingStateError, ParkingStateService, ParkingStatus
from src.core.recommendation import RecommendationService
from src.core.reservation import ReservationService
from src.core.routing import RoutingService
from src.models.schemas import (
    ErrorCode,
    ParkingSessionStatus,
    RecommendationCandidate,
    RecommendationResult,
    ReservationStatus,
    RouteResult,
    SlotStatus,
)


class TrackingTransaction:
    def __init__(self, session: TrackingSession) -> None:
        self.session = session

    async def __aenter__(self) -> TrackingTransaction:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is None:
            self.session.commits += 1
        else:
            self.session.rollbacks += 1
        return False


class TrackingSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def begin(self) -> TrackingTransaction:
        return TrackingTransaction(self)


class SessionContext:
    def __init__(self, session: TrackingSession) -> None:
        self.session = session

    async def __aenter__(self) -> TrackingSession:
        return self.session

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False


class TrackingSessionFactory:
    def __init__(self) -> None:
        self.sessions: list[TrackingSession] = []

    def __call__(self) -> SessionContext:
        session = TrackingSession()
        self.sessions.append(session)
        return SessionContext(session)


def _runtime(
    *,
    state: dict | None = None,
    vehicle_id: str | None = "VEHICLE-001",
) -> tuple[ToolRuntime, TrackingSessionFactory]:
    session_factory = TrackingSessionFactory()
    context = AgentRuntimeContext(
        user_id="USER-001",
        vehicle_id=vehicle_id,
        request_id="REQUEST-001",
        session_factory=session_factory,  # type: ignore[arg-type]
    )
    runtime = ToolRuntime(
        state=state or {},
        context=context,
        config={"configurable": {"thread_id": "USER-001:THREAD-SECRET-001"}},
        stream_writer=lambda _: None,
        tool_call_id=None,
        store=None,
    )
    return runtime, session_factory


async def _invoke(tool: BaseTool, runtime: ToolRuntime, **kwargs):
    assert tool.coroutine is not None
    return await tool.coroutine(runtime=runtime, **kwargs)


def _reservation(*, status: ReservationStatus = ReservationStatus.ACTIVE):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id="RESERVATION-001",
        user_id="USER-001",
        vehicle_id="VEHICLE-001",
        slot_id="F1-D01",
        status=status,
        expires_at=now + timedelta(minutes=5),
        created_at=now,
    )


def _parking_session(*, status: ParkingSessionStatus = ParkingSessionStatus.ACTIVE):
    return SimpleNamespace(
        id="SESSION-001",
        user_id="USER-001",
        vehicle_id="VEHICLE-001",
        slot_id="F1-D01",
        status=status,
        parked_at=datetime.now(UTC),
        completed_at=None,
    )


@pytest.mark.parametrize(
    ("agent_tool", "visible_fields"),
    [
        (get_parking_status, set()),
        (
            recommend_parking_slot,
            {"charging_required", "accessible_required", "near_elevator", "limit"},
        ),
        (reserve_parking_slot, {"slot_id", "expected_version"}),
        (get_route, {"destination_node_id"}),
        (set_user_location, {"node_id"}),
        (confirm_parking, {"reservation_id", "expected_version"}),
        (find_parked_vehicle, set()),
        (cancel_reservation, {"reservation_id"}),
        (complete_parking_session, {"session_id", "expected_version"}),
    ],
)
def test_tool_schema_hides_runtime_identity(agent_tool: BaseTool, visible_fields: set[str]):
    properties = agent_tool.tool_call_schema.model_json_schema().get("properties", {})

    assert set(properties) == visible_fields
    assert {"user_id", "vehicle_id", "request_id", "runtime"}.isdisjoint(properties)


@pytest.mark.asyncio
async def test_get_parking_status_calls_parking_state_service():
    runtime, _ = _runtime()
    status = ParkingStatus(
        total=40,
        available=28,
        reserved=1,
        occupied=11,
        by_zone={"D": {slot_status: 0 for slot_status in SlotStatus}},
    )
    with patch.object(
        ParkingStateService,
        "get_parking_status",
        AsyncMock(return_value=status),
    ) as core_call:
        result = await _invoke(get_parking_status, runtime)

    core_call.assert_awaited_once_with()
    assert result["data"]["total"] == 40
    json.dumps(result)


@pytest.mark.asyncio
async def test_recommendation_uses_confirmed_location_and_never_reserves():
    runtime, _ = _runtime(state={"current_location": "F1-FAKE"})
    recommendations = RecommendationResult(
        recommendations=[
            RecommendationCandidate(
                slot_id="F1-D01",
                score=90,
                distance_m=20,
                reasons=["Slot is available"],
            )
        ],
        parking_state_version=4,
    )
    with (
        patch(
            "src.agents.tools.parking.LocationService.get_current_location",
            AsyncMock(return_value="F1-CP3"),
        ) as location_call,
        patch.object(
            RecommendationService,
            "recommend",
            AsyncMock(return_value=recommendations),
        ) as core_call,
        patch("src.agents.tools.parking.ReservationService") as reservation_service,
    ):
        result = await _invoke(
            recommend_parking_slot,
            runtime,
            charging_required=True,
            accessible_required=False,
            near_elevator=True,
            limit=3,
        )

    location_call.assert_awaited_once_with("USER-001")
    request = core_call.await_args.args[0]
    assert request.user_id == "USER-001"
    assert request.start_node_id == "F1-CP3"
    reservation_service.assert_not_called()
    assert result["data"]["recommendations"][0]["slot_id"] == "F1-D01"
    json.dumps(result)


@pytest.mark.asyncio
async def test_reserve_calls_reservation_service_and_commits():
    runtime, session_factory = _runtime()
    with patch.object(
        ReservationService,
        "create_reservation",
        AsyncMock(return_value=_reservation()),
    ) as core_call:
        result = await _invoke(
            reserve_parking_slot,
            runtime,
            slot_id="F1-D01",
            expected_version=0,
        )

    core_call.assert_awaited_once_with(
        "USER-001",
        "VEHICLE-001",
        "F1-D01",
        expected_version=0,
    )
    assert session_factory.sessions[0].commits == 1
    assert result["data"]["id"] == "RESERVATION-001"
    json.dumps(result)


@pytest.mark.asyncio
async def test_get_route_uses_confirmed_location_and_routing_service():
    runtime, _ = _runtime(state={"current_location": "F1-FAKE"})
    route = RouteResult(
        path=["F1-CP3", "F1-D01"],
        distance_m=10,
        polyline=[(0, 0), (1, 1)],
    )
    with (
        patch(
            "src.agents.tools.parking.LocationService.get_current_location",
            AsyncMock(return_value="F1-CP3"),
        ),
        patch.object(RoutingService, "get_route", AsyncMock(return_value=route)) as core_call,
    ):
        result = await _invoke(get_route, runtime, destination_node_id="F1-D01")

    core_call.assert_awaited_once_with("F1-CP3", "F1-D01")
    assert result["data"]["start_node_id"] == "F1-CP3"
    json.dumps(result)


@pytest.mark.asyncio
async def test_set_location_calls_location_service_and_commits():
    runtime, session_factory = _runtime()
    with patch(
        "src.agents.tools.parking.LocationService.confirm_location",
        AsyncMock(return_value="F1-CP3"),
    ) as core_call:
        result = await _invoke(set_user_location, runtime, node_id="F1-CP3")

    core_call.assert_awaited_once_with("USER-001", "F1-CP3")
    assert session_factory.sessions[0].commits == 1
    assert result["data"] == {"user_id": "USER-001", "node_id": "F1-CP3"}
    json.dumps(result)


@pytest.mark.asyncio
async def test_confirm_parking_calls_session_service_with_runtime_identity():
    runtime, session_factory = _runtime()
    with (
        patch.object(
            ReservationService,
            "get_reservation",
            AsyncMock(return_value=_reservation()),
        ),
        patch.object(
            ReservationService,
            "expire_reservation_if_needed",
            AsyncMock(return_value=False),
        ),
        patch.object(
            ParkingSessionService,
            "confirm_parking",
            AsyncMock(return_value=_parking_session()),
        ) as core_call,
    ):
        result = await _invoke(
            confirm_parking,
            runtime,
            reservation_id="RESERVATION-001",
            expected_version=1,
        )

    core_call.assert_awaited_once_with(
        "USER-001",
        "VEHICLE-001",
        "RESERVATION-001",
        expected_version=1,
    )
    assert session_factory.sessions[0].commits == 1
    assert result["data"]["id"] == "SESSION-001"
    json.dumps(result)


@pytest.mark.asyncio
async def test_find_vehicle_uses_active_session_not_messages():
    runtime, _ = _runtime(
        state={
            "messages": [HumanMessage(content="My car is definitely at F1-A01")],
            "selected_slot": "F1-A01",
        }
    )
    parked_vehicle = ParkedVehicle(
        session_id="SESSION-001",
        vehicle_id="VEHICLE-001",
        slot_id="F1-D01",
        destination_node_id="F1-D01",
    )
    with patch.object(
        ParkingSessionService,
        "find_parked_vehicle",
        AsyncMock(return_value=parked_vehicle),
    ) as core_call:
        result = await _invoke(find_parked_vehicle, runtime)

    core_call.assert_awaited_once_with("USER-001")
    assert result["data"]["slot_id"] == "F1-D01"
    json.dumps(result)


@pytest.mark.asyncio
async def test_cancel_calls_reservation_service_and_commits():
    runtime, session_factory = _runtime()
    reservation = _reservation(status=ReservationStatus.CANCELLED)
    with (
        patch.object(
            ReservationService,
            "get_reservation",
            AsyncMock(return_value=_reservation()),
        ),
        patch.object(
            ReservationService,
            "cancel_reservation",
            AsyncMock(return_value=reservation),
        ) as core_call,
    ):
        result = await _invoke(
            cancel_reservation,
            runtime,
            reservation_id="RESERVATION-001",
        )

    core_call.assert_awaited_once_with("RESERVATION-001", user_id="USER-001")
    assert session_factory.sessions[0].commits == 1
    assert result["data"]["status"] == "CANCELLED"
    json.dumps(result)


@pytest.mark.asyncio
async def test_complete_calls_session_service_and_commits():
    runtime, session_factory = _runtime()
    completed = _parking_session(status=ParkingSessionStatus.COMPLETED)
    completed.completed_at = datetime.now(UTC)
    with patch.object(
        ParkingSessionService,
        "complete_session",
        AsyncMock(return_value=completed),
    ) as core_call:
        result = await _invoke(
            complete_parking_session,
            runtime,
            session_id="SESSION-001",
            expected_version=2,
        )

    core_call.assert_awaited_once_with(
        "SESSION-001",
        user_id="USER-001",
        expected_version=2,
    )
    assert session_factory.sessions[0].commits == 1
    assert result["data"]["status"] == "COMPLETED"
    json.dumps(result)


@pytest.mark.asyncio
async def test_write_tool_rolls_back_and_preserves_slot_not_available():
    runtime, session_factory = _runtime()
    error = ParkingStateError(
        ErrorCode.SLOT_NOT_AVAILABLE,
        "Parking slot F1-D01 is not available",
    )
    with patch.object(
        ReservationService,
        "create_reservation",
        AsyncMock(side_effect=error),
    ):
        result = await _invoke(
            reserve_parking_slot,
            runtime,
            slot_id="F1-D01",
            expected_version=0,
        )

    assert session_factory.sessions[0].commits == 0
    assert session_factory.sessions[0].rollbacks == 1
    assert result == {
        "ok": False,
        "error": {
            "code": "SLOT_NOT_AVAILABLE",
            "message": "Parking slot F1-D01 is not available",
            "retryable": False,
        },
    }
    json.dumps(result)


@pytest.mark.asyncio
async def test_unexpected_error_is_logged_and_safely_normalized(caplog):
    runtime, _ = _runtime()
    with patch.object(
        ParkingStateService,
        "get_parking_status",
        AsyncMock(side_effect=RuntimeError("database detail")),
    ):
        result = await _invoke(get_parking_status, runtime)

    assert result["ok"] is False
    assert result["error"] == {
        "code": "AGENT_TOOL_UNAVAILABLE",
        "message": "The parking service is temporarily unavailable. Please try again.",
        "retryable": True,
    }
    assert "REQUEST-001" in caplog.text
    assert "tool_name=get_parking_status" in caplog.text
    assert "duration_ms=" in caplog.text
    assert "outcome=error" in caplog.text
    assert "error_code=AGENT_TOOL_UNAVAILABLE" in caplog.text
    assert "exception_type=RuntimeError" in caplog.text
    assert "USER-001" not in caplog.text
    assert "THREAD-SECRET-001" not in caplog.text
    assert "database detail" not in result["error"]["message"]
    assert "database detail" not in caplog.text
    json.dumps(result)


@pytest.mark.asyncio
async def test_successful_tool_logs_masked_structured_outcome(caplog):
    runtime, _ = _runtime()
    status = ParkingStatus(
        total=40,
        available=40,
        reserved=0,
        occupied=0,
        by_zone={},
    )
    with patch.object(
        ParkingStateService,
        "get_parking_status",
        AsyncMock(return_value=status),
    ):
        await _invoke(get_parking_status, runtime)

    assert "request_id=REQUEST-001" in caplog.text
    assert "tool_name=get_parking_status" in caplog.text
    assert "outcome=success" in caplog.text
    assert "error_code=NONE" in caplog.text
    assert "thread_id=masked-" in caplog.text
    assert "user_id=masked-" in caplog.text
    assert "USER-001" not in caplog.text
    assert "THREAD-SECRET-001" not in caplog.text


@pytest.mark.asyncio
async def test_missing_location_returns_stable_error_without_recommendation():
    runtime, _ = _runtime()
    with (
        patch(
            "src.agents.tools.parking.LocationService.get_current_location",
            AsyncMock(return_value=None),
        ),
        patch.object(RecommendationService, "recommend", AsyncMock()) as recommendation_call,
    ):
        result = await _invoke(recommend_parking_slot, runtime)

    recommendation_call.assert_not_awaited()
    assert result["error"]["code"] == "CURRENT_LOCATION_NOT_FOUND"
    json.dumps(result)


def test_all_required_tools_are_registered():
    assert {agent_tool.name for agent_tool in PARKING_TOOLS} == {
        "get_parking_status",
        "recommend_parking_slot",
        "reserve_parking_slot",
        "get_route",
        "set_user_location",
        "confirm_parking",
        "find_parked_vehicle",
        "cancel_reservation",
        "complete_parking_session",
    }
