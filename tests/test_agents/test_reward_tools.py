"""The agent may explain public Points policy/catalog, never personal rewards."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.prebuilt import ToolRuntime

from src.agents.context import AgentRuntimeContext
from src.agents.tools import AGENT_TOOLS, PARKING_TOOLS
from src.agents.tools.rewards import (
    REWARD_TOOLS,
    get_reward_catalog,
    get_reward_configuration,
)


class Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class Session:
    def begin(self):
        return Transaction()


class SessionContext:
    async def __aenter__(self):
        return Session()

    async def __aexit__(self, *_args):
        return False


def _runtime() -> ToolRuntime:
    return ToolRuntime(
        state={},
        context=AgentRuntimeContext(
            user_id="USER-001",
            vehicle_id="VEHICLE-001",
            request_id="REQUEST-001",
            session_factory=SessionContext,
        ),
        config={"configurable": {"thread_id": "USER-001:THREAD"}},
        stream_writer=lambda _: None,
        tool_call_id=None,
        store=None,
    )  # type: ignore[arg-type]


async def _invoke(tool, runtime):
    assert tool.coroutine is not None
    return await tool.coroutine(runtime=runtime)


@pytest.mark.parametrize("agent_tool", REWARD_TOOLS)
def test_reward_schemas_expose_no_identity_or_mutation_input(agent_tool):
    properties = agent_tool.tool_call_schema.model_json_schema().get("properties", {})
    assert set(properties).isdisjoint(
        {"user_id", "vehicle_id", "request_id", "runtime", "catalog_item_id"}
    )


@pytest.mark.asyncio
async def test_configuration_and_catalog_are_authoritative():
    catalog = [
        SimpleNamespace(
            id="CAT-1",
            code="ODD",
            name="Database reward",
            points_cost=123,
            free_minutes=47,
            validity_days=9,
            version=0,
        )
    ]
    with patch(
        "src.agents.tools.rewards.RewardCatalogService.list_active",
        AsyncMock(return_value=catalog),
    ):
        assert (await _invoke(get_reward_configuration, _runtime()))["ok"] is True
        result = await _invoke(get_reward_catalog, _runtime())
    assert result["data"][0] == {
        "id": "CAT-1",
        "code": "ODD",
        "name": "Database reward",
        "points_cost": 123,
        "free_minutes": 47,
        "validity_days": 9,
        "version": 0,
    }


def test_reward_boundary_and_agent_tool_set():
    reward_names = {tool.name for tool in REWARD_TOOLS}
    assert reward_names == {
        "get_reward_configuration",
        "get_reward_catalog",
    }

    names = [tool.name for tool in AGENT_TOOLS]
    assert len(names) == len(set(names))
    assert {tool.name for tool in PARKING_TOOLS}.issubset(names)
    assert "get_my_reward_summary" not in names
    assert "get_my_vouchers" not in names
    assert not any(
        any(word in name for word in ("redeem", "spend", "issue", "refund", "apply"))
        for name in names
    )
