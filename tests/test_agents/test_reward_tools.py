"""Agent reward tools expose policy/catalog only, never a personal wallet."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.prebuilt import ToolRuntime

from src.agents.context import AgentRuntimeContext
from src.agents.tools import AGENT_TOOLS, PARKING_TOOLS
from src.agents.tools.rewards import REWARD_TOOLS, get_reward_catalog, get_reward_configuration


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


def _runtime(user_id: str = "USER-001") -> ToolRuntime:
    return ToolRuntime(
        state={},
        context=AgentRuntimeContext(
            user_id=user_id,
            vehicle_id="VEHICLE-001",
            request_id="REQUEST-001",
            session_factory=SessionContext,  # type: ignore[arg-type]
        ),
        config={"configurable": {"thread_id": "USER-001:THREAD"}},
        stream_writer=lambda _: None,
        tool_call_id=None,
        store=None,
    )


async def _invoke(tool, runtime):
    assert tool.coroutine is not None
    return await tool.coroutine(runtime=runtime)


@pytest.mark.parametrize("agent_tool", REWARD_TOOLS)
def test_reward_tool_schemas_hide_identity_and_mutation_inputs(agent_tool):
    properties = agent_tool.tool_call_schema.model_json_schema().get("properties", {})
    assert set(properties).isdisjoint(
        {"user_id", "vehicle_id", "request_id", "runtime", "authentication", "catalog_item_id"}
    )


@pytest.mark.asyncio
async def test_reward_tools_use_trusted_runtime_for_general_policy_and_catalog_only():
    runtime = _runtime("USER-001")
    catalog = [
        SimpleNamespace(
            id="CAT-1",
            code="ODD",
            name="Database reward",
            points_cost=123,
            free_minutes=44,
            validity_days=9,
            version=0,
        )
    ]
    with patch("src.agents.tools.rewards.RewardCatalogService.list_active", AsyncMock(return_value=catalog)):
        configuration = await _invoke(get_reward_configuration, runtime)
        catalog_result = await _invoke(get_reward_catalog, runtime)
    assert configuration["ok"] is True
    assert "redemption_enabled" in configuration["data"]
    assert catalog_result["data"] == [
        {
            "id": "CAT-1",
            "code": "ODD",
            "name": "Database reward",
            "points_cost": 123,
            "free_minutes": 44,
            "validity_days": 9,
            "version": 0,
        }
    ]


def test_combined_agent_tools_are_unique_without_personal_or_mutating_reward_tools():
    names = [tool.name for tool in AGENT_TOOLS]
    assert len(names) == len(set(names))
    assert {"get_reward_configuration", "get_reward_catalog"}.issubset(names)
    assert {tool.name for tool in PARKING_TOOLS}.issubset(names)
    assert not any(
        "reward" in name and any(word in name for word in ("my", "balance", "voucher"))
        for name in names
    )
    assert not any(
        any(word in name for word in ("redeem", "spend", "issue", "refund", "apply"))
        for name in names
    )
