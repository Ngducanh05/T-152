from __future__ import annotations

from collections.abc import AsyncGenerator, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.agents.context import AgentRuntimeContext
from src.agents.graph import build_graph
from src.agents.tools import PARKING_TOOLS
from src.core.config import get_settings
from src.core.db_models import (
    Base,
    ParkingReservation,
    ParkingSession,
    ParkingSlot,
    ParkingUser,
    Vehicle,
)
from src.core.seed import seed_if_missing
from src.models.schemas import ParkingSessionStatus, ReservationStatus, SlotStatus


class FlowScriptedModel(FakeMessagesListChatModel):
    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> FlowScriptedModel:
        return self

    def load(self, responses: list[AIMessage]) -> None:
        self.responses = responses
        self.i = 0


@dataclass(slots=True)
class AgentFlow:
    graph: Any
    model: FlowScriptedModel
    session_factory: async_sessionmaker[AsyncSession]
    call_index: int = 0

    def tool_call(self, name: str, arguments: dict[str, Any]) -> AIMessage:
        self.call_index += 1
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": name,
                    "args": arguments,
                    "id": f"flow-call-{self.call_index}",
                    "type": "tool_call",
                }
            ],
        )

    async def turn(
        self,
        message: str,
        responses: list[AIMessage],
        *,
        thread_id: str = "USER-001:FLOW-001",
        user_id: str = "USER-001",
        vehicle_id: str | None = "VEHICLE-001",
    ) -> dict[str, Any]:
        self.model.load(responses)
        return await self.graph.ainvoke(
            {"messages": [HumanMessage(content=message)]},
            config={"configurable": {"thread_id": thread_id}},
            context=AgentRuntimeContext(
                user_id=user_id,
                vehicle_id=vehicle_id,
                request_id=f"REQUEST-{self.call_index + 1}",
                session_factory=self.session_factory,
            ),
        )


@pytest_asyncio.fixture
async def agent_flow() -> AsyncGenerator[AgentFlow, None]:
    database_url = get_settings().database_url
    schema_name = f"test_agent_tool_flow_{uuid4().hex}"
    admin_engine = create_async_engine(database_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as connection:
        await connection.execute(CreateSchema(schema_name))

    engine = create_async_engine(
        database_url,
        connect_args={"server_settings": {"search_path": schema_name}},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await seed_if_missing(session)

    model = FlowScriptedModel(responses=[AIMessage(content="unused")])
    flow = AgentFlow(
        graph=build_graph(
            model,
            tools=PARKING_TOOLS,
            checkpointer=InMemorySaver(),
        ),
        model=model,
        session_factory=session_factory,
    )
    try:
        yield flow
    finally:
        await engine.dispose()
        async with admin_engine.connect() as connection:
            await connection.execute(DropSchema(schema_name, cascade=True))
        await admin_engine.dispose()


def _tool_names(state: dict[str, Any]) -> list[str]:
    return [
        message.name
        for message in state["messages"]
        if isinstance(message, ToolMessage) and message.name is not None
    ]


@pytest.mark.asyncio
async def test_full_agent_core_tool_flow(agent_flow: AgentFlow):
    state = await agent_flow.turn(
        "Tôi đang ở Entrance.",
        [
            agent_flow.tool_call("set_user_location", {"node_id": "F1-ENTRANCE"}),
            AIMessage(content="Đã xác nhận vị trí Entrance."),
        ],
    )
    assert state["current_location"] == "F1-ENTRANCE"

    state = await agent_flow.turn(
        "Tìm chỗ có sạc gần thang máy.",
        [
            agent_flow.tool_call(
                "recommend_parking_slot",
                {
                    "charging_required": True,
                    "accessible_required": False,
                    "near_elevator": True,
                    "limit": 3,
                },
            ),
            AIMessage(content="Đây là các ô EV đang trống."),
        ],
    )
    recommended_slot = state["recommended_slot_ids"][0]
    assert recommended_slot.startswith(("F1-C", "F1-D"))
    assert "active_reservation_id" not in state
    assert _tool_names(state) == ["set_user_location", "recommend_parking_slot"]
    async with agent_flow.session_factory() as session:
        active_reservations = await session.scalar(
            select(func.count())
            .select_from(ParkingReservation)
            .where(ParkingReservation.status == ReservationStatus.ACTIVE)
        )
    assert active_reservations == 0

    state = await agent_flow.turn(
        f"Tôi chọn {recommended_slot}.",
        [
            agent_flow.tool_call(
                "reserve_parking_slot",
                {"slot_id": recommended_slot, "expected_version": 0},
            ),
            AIMessage(content="Đã giữ ô bạn chọn."),
        ],
    )
    reservation_id = state["active_reservation_id"]
    assert state["selected_slot"] == recommended_slot
    assert state["recommended_slot_ids"] == []
    assert state["route"] is None

    state = await agent_flow.turn(
        "Chỉ đường tới đó.",
        [
            agent_flow.tool_call(
                "get_route",
                {"destination_node_id": recommended_slot},
            ),
            AIMessage(content="Đây là tuyến đường tới ô đã chọn."),
        ],
    )
    assert state["tool_result"]["data"]["start_node_id"] == "F1-ENTRANCE"
    assert state["tool_result"]["data"]["path"][-1] == recommended_slot
    assert state["route"].path[-1] == recommended_slot

    state = await agent_flow.turn(
        "Tôi đã đỗ.",
        [
            agent_flow.tool_call(
                "confirm_parking",
                {"reservation_id": reservation_id, "expected_version": 1},
            ),
            AIMessage(content="Đã xác nhận xe được đỗ."),
        ],
    )
    session_id = state["active_session_id"]
    assert state["route"] is None

    state = await agent_flow.turn(
        "Tôi ở CP3, chỉ đường tới xe.",
        [
            agent_flow.tool_call("set_user_location", {"node_id": "F1-CP3"}),
            agent_flow.tool_call("find_parked_vehicle", {}),
            agent_flow.tool_call(
                "get_route",
                {"destination_node_id": recommended_slot},
            ),
            AIMessage(content="Đây là tuyến đường từ CP3 tới xe của bạn."),
        ],
    )

    assert _tool_names(state) == [
        "set_user_location",
        "recommend_parking_slot",
        "reserve_parking_slot",
        "get_route",
        "confirm_parking",
        "set_user_location",
        "find_parked_vehicle",
        "get_route",
    ]
    assert state["current_location"] == "F1-CP3"
    assert state["selected_slot"] == recommended_slot
    assert state["active_session_id"] == session_id
    assert state["intent"] == "GET_ROUTE_TO_CAR"
    assert state["tool_result"]["data"]["start_node_id"] == "F1-CP3"
    assert state["tool_result"]["data"]["path"][-1] == recommended_slot

    async with agent_flow.session_factory() as session:
        reservation = await session.get(ParkingReservation, reservation_id)
        parking_session = await session.get(ParkingSession, session_id)
        slot = await session.get(ParkingSlot, recommended_slot)
        user = await session.get(ParkingUser, "USER-001")
    assert reservation is not None and reservation.status is ReservationStatus.CONFIRMED
    assert parking_session is not None
    assert parking_session.status is ParkingSessionStatus.ACTIVE
    assert slot is not None and slot.status is SlotStatus.OCCUPIED
    assert user is not None and user.current_node_id == "F1-CP3"


@pytest.mark.asyncio
async def test_slot_just_reserved_by_another_user_is_not_faked_as_success(
    agent_flow: AgentFlow,
):
    async with agent_flow.session_factory() as session, session.begin():
        session.add(ParkingUser(id="USER-002", display_name="Second User"))
        session.add(
            Vehicle(
                id="VEHICLE-002",
                user_id="USER-002",
                plate_number="51A-00002",
                requires_charging=False,
            )
        )

    slot_id = "F1-D10"
    winner = await agent_flow.turn(
        "Tôi chọn D10.",
        [
            agent_flow.tool_call(
                "reserve_parking_slot",
                {"slot_id": slot_id, "expected_version": 0},
            ),
            AIMessage(content="Đã giữ ô cho user thứ hai."),
        ],
        thread_id="USER-002:FLOW-WINNER",
        user_id="USER-002",
        vehicle_id="VEHICLE-002",
    )
    assert winner["active_reservation_id"]

    loser = await agent_flow.turn(
        "Tôi cũng chọn D10.",
        [
            agent_flow.tool_call(
                "reserve_parking_slot",
                {"slot_id": slot_id, "expected_version": 0},
            ),
            AIMessage(content="Ô đó vừa được người khác giữ; tôi chưa giữ ô nào cho bạn."),
        ],
        thread_id="USER-001:FLOW-LOSER",
    )

    assert loser["tool_result"]["error"]["code"] == "SLOT_NOT_AVAILABLE"
    assert loser["error"].startswith("SLOT_NOT_AVAILABLE:")
    assert "active_reservation_id" not in loser
    async with agent_flow.session_factory() as session:
        active = list(
            await session.scalars(
                select(ParkingReservation).where(
                    ParkingReservation.slot_id == slot_id,
                    ParkingReservation.status == ReservationStatus.ACTIVE,
                )
            )
        )
    assert len(active) == 1 and active[0].user_id == "USER-002"


@pytest.mark.asyncio
async def test_expired_reservation_is_released_without_fake_session(agent_flow: AgentFlow):
    slot_id = "F1-D09"
    reserved = await agent_flow.turn(
        "Tôi chọn D09.",
        [
            agent_flow.tool_call(
                "reserve_parking_slot",
                {"slot_id": slot_id, "expected_version": 0},
            ),
            AIMessage(content="Đã giữ ô."),
        ],
        thread_id="USER-001:FLOW-EXPIRED",
    )
    reservation_id = reserved["active_reservation_id"]
    async with agent_flow.session_factory() as session, session.begin():
        reservation = await session.get(ParkingReservation, reservation_id)
        assert reservation is not None
        expired_at = datetime.now(UTC) - timedelta(seconds=1)
        reservation.created_at = expired_at - timedelta(minutes=5)
        reservation.expires_at = expired_at

    expired = await agent_flow.turn(
        "Tôi đã đỗ.",
        [
            agent_flow.tool_call(
                "confirm_parking",
                {"reservation_id": reservation_id, "expected_version": 1},
            ),
            AIMessage(content="Chỗ giữ đã hết hạn; chưa có phiên đỗ xe nào được tạo."),
        ],
        thread_id="USER-001:FLOW-EXPIRED",
    )

    assert expired["tool_result"]["error"]["code"] == "RESERVATION_EXPIRED"
    assert "active_session_id" not in expired
    async with agent_flow.session_factory() as session:
        reservation = await session.get(ParkingReservation, reservation_id)
        slot = await session.get(ParkingSlot, slot_id)
        session_count = await session.scalar(select(func.count()).select_from(ParkingSession))
    assert reservation is not None and reservation.status is ReservationStatus.EXPIRED
    assert slot is not None and slot.status is SlotStatus.AVAILABLE
    assert session_count == 0


@pytest.mark.asyncio
async def test_missing_location_vehicle_and_active_session_use_stable_errors(
    agent_flow: AgentFlow,
):
    async with agent_flow.session_factory() as session, session.begin():
        user = await session.get(ParkingUser, "USER-001")
        assert user is not None
        user.current_node_id = None

    missing_location = await agent_flow.turn(
        "Tìm chỗ có sạc gần thang máy.",
        [
            agent_flow.tool_call(
                "recommend_parking_slot",
                {"charging_required": True, "near_elevator": True},
            ),
            AIMessage(content="Bạn đang ở vị trí nào trong bãi xe?"),
        ],
        thread_id="USER-001:MISSING-LOCATION",
    )
    assert missing_location["tool_result"]["error"]["code"] == (
        "CURRENT_LOCATION_NOT_FOUND"
    )
    assert "current_location" in missing_location["missing_fields"]
    assert missing_location["recommended_slot_ids"] == []

    missing_vehicle = await agent_flow.turn(
        "Tôi chọn D08.",
        [
            agent_flow.tool_call(
                "reserve_parking_slot",
                {"slot_id": "F1-D08", "expected_version": 0},
            ),
            AIMessage(content="Bạn muốn dùng xe nào để giữ chỗ?"),
        ],
        thread_id="USER-001:MISSING-VEHICLE",
        vehicle_id=None,
    )
    assert missing_vehicle["tool_result"]["error"]["code"] == "VEHICLE_NOT_FOUND"
    assert "vehicle_id" in missing_vehicle["missing_fields"]
    assert "active_reservation_id" not in missing_vehicle

    no_session = await agent_flow.turn(
        "Xe của tôi ở đâu?",
        [
            agent_flow.tool_call("find_parked_vehicle", {}),
            AIMessage(content="Bạn chưa có phiên đỗ xe đang hoạt động."),
        ],
        thread_id="USER-001:NO-SESSION",
    )
    assert no_session["tool_result"]["error"]["code"] == "ACTIVE_SESSION_NOT_FOUND"
    assert "selected_slot" not in no_session
