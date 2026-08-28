from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolRuntime

from src.agents.context import AgentRuntimeContext
from src.agents.tools import AGENT_TOOLS, PARKING_TOOLS
from src.agents.tools.rewards import (
    REWARD_TOOLS,
    get_my_reward_summary,
    get_reward_configuration,
)
from src.core.reward import RewardError, RewardService
from src.core.slot_observation import SlotObservationService
from src.models.schemas import ErrorCode, RewardSummary


class _FakeTransaction:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is None:
            self.session.commits += 1
        else:
            self.session.rollbacks += 1
        return False


class _FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def begin(self) -> _FakeTransaction:
        return _FakeTransaction(self)


class _FakeSessionContext:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    async def __aenter__(self) -> _FakeSession:
        return self.session

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False


class _FakeSessionFactory:
    def __init__(self) -> None:
        self.sessions: list[_FakeSession] = []

    def __call__(self) -> _FakeSessionContext:
        session = _FakeSession()
        self.sessions.append(session)
        return _FakeSessionContext(session)


def _runtime(*, user_id: str = "USER-001") -> tuple[ToolRuntime, _FakeSessionFactory]:
    session_factory = _FakeSessionFactory()
    context = AgentRuntimeContext(
        user_id=user_id,
        vehicle_id="VEHICLE-001",
        request_id="REQUEST-001",
        session_factory=session_factory,  # type: ignore[arg-type]
    )
    runtime = ToolRuntime(
        state={},
        context=context,
        config={"configurable": {"thread_id": f"{user_id}:THREAD-001"}},
        stream_writer=lambda _: None,
        tool_call_id=None,
        store=None,
    )
    return runtime, session_factory


async def _invoke(tool: BaseTool, runtime: ToolRuntime):
    assert tool.coroutine is not None
    return await tool.coroutine(runtime=runtime)


@pytest.mark.parametrize("agent_tool", [get_reward_configuration, get_my_reward_summary])
def test_reward_tool_schema_hides_runtime_identity(agent_tool: BaseTool):
    properties = agent_tool.tool_call_schema.model_json_schema().get("properties", {})

    assert properties == {}
    assert {"user_id", "vehicle_id", "request_id", "runtime"}.isdisjoint(properties)


@pytest.mark.asyncio
async def test_get_reward_configuration_reads_live_settings_not_hardcoded_values():
    runtime, _ = _runtime()
    fake_settings = SimpleNamespace(
        adjacent_observation_reward_points=42,
        wrong_parking_report_reward_points=99,
        contribution_daily_points_limit=250,
    )
    with patch(
        "src.agents.tools.rewards.get_settings",
        return_value=fake_settings,
    ) as settings_call:
        result = await _invoke(get_reward_configuration, runtime)

    settings_call.assert_called_once_with()
    assert result["data"] == {
        "adjacent_observation_reward_points": 42,
        "wrong_parking_report_reward_points": 99,
        "contribution_daily_points_limit": 250,
    }
    json.dumps(result)


@pytest.mark.asyncio
async def test_get_my_reward_summary_expires_pending_before_reading_the_ledger():
    """Regression test: without this expiry sweep, an observation whose
    verification window lapsed keeps its reward PENDING and the agent
    reports inflated pending_points/daily_pending_points, unlike the REST
    /rewards/users/{user_id}/summary endpoint which sweeps first. Locks in
    the call ORDER (expire must run before summary — swapping them would
    still pass a "both were called" assertion but not this one) and that
    write=True actually commits the sweep instead of silently rolling it
    back when the fake session closes.
    """
    runtime, session_factory = _runtime(user_id="USER-042")
    summary = RewardSummary(
        available_points=30,
        pending_points=10,
        verified_contributions=3,
        daily_pending_points=10,
        daily_earned_points=20,
        daily_limit_points=100,
    )
    events: list[str] = []

    async def fake_expire_pending(self: SlotObservationService) -> int:
        events.append("expire")
        return 0

    async def fake_get_summary(self: RewardService, user_id: str) -> RewardSummary:
        events.append("summary")
        assert user_id == "USER-042"
        return summary

    with (
        patch.object(SlotObservationService, "expire_pending", fake_expire_pending),
        patch.object(RewardService, "get_summary", fake_get_summary),
    ):
        result = await _invoke(get_my_reward_summary, runtime)

    assert events == ["expire", "summary"]
    assert session_factory.sessions[-1].commits == 1
    assert session_factory.sessions[-1].rollbacks == 0
    assert result["data"]["available_points"] == 30
    assert result["data"]["daily_limit_points"] == 100
    json.dumps(result)


@pytest.mark.asyncio
async def test_get_my_reward_summary_maps_reward_error_to_a_stable_code():
    runtime, session_factory = _runtime()
    with (
        patch.object(SlotObservationService, "expire_pending", AsyncMock(return_value=0)),
        patch.object(
            RewardService,
            "get_summary",
            AsyncMock(
                side_effect=RewardError(
                    ErrorCode.USER_NOT_FOUND, "Parking user USER-001 was not found"
                )
            ),
        ),
    ):
        result = await _invoke(get_my_reward_summary, runtime)

    assert result == {
        "ok": False,
        "error": {
            "code": "USER_NOT_FOUND",
            "message": "Parking user USER-001 was not found",
            "retryable": False,
        },
    }
    # A domain error inside the write transaction must roll back, not
    # silently commit a partial expiry sweep.
    assert session_factory.sessions[-1].commits == 0
    assert session_factory.sessions[-1].rollbacks == 1


def test_all_reward_tools_are_registered():
    assert {agent_tool.name for agent_tool in REWARD_TOOLS} == {
        "get_reward_configuration",
        "get_my_reward_summary",
    }


def test_agent_tools_combine_parking_and_reward_tools_without_duplicates():
    names = [agent_tool.name for agent_tool in AGENT_TOOLS]

    assert len(names) == 12
    assert len(set(names)) == len(names)
    assert set(names) == {t.name for t in PARKING_TOOLS} | {t.name for t in REWARD_TOOLS}
