"""Read-only reward agent tools use only trusted runtime identity."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.prebuilt import ToolRuntime

from src.agents.context import AgentRuntimeContext
from src.agents.tools import AGENT_TOOLS, PARKING_TOOLS
from src.agents.tools.rewards import (
    REWARD_TOOLS,
    get_my_reward_summary,
    get_my_vouchers,
    get_reward_catalog,
    get_reward_configuration,
)
from src.models.schemas import ParkingVoucherStatus, RewardSummary


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
        context=AgentRuntimeContext(user_id=user_id, vehicle_id="VEHICLE-001", request_id="REQUEST-001", session_factory=SessionContext),  # type: ignore[arg-type]
        config={"configurable": {"thread_id": "USER-001:THREAD"}}, stream_writer=lambda _: None, tool_call_id=None, store=None,
    )


async def _invoke(tool, runtime):
    assert tool.coroutine is not None
    return await tool.coroutine(runtime=runtime)


@pytest.mark.parametrize("agent_tool", REWARD_TOOLS)
def test_reward_tool_schemas_hide_identity_and_mutation_inputs(agent_tool):
    properties = agent_tool.tool_call_schema.model_json_schema().get("properties", {})
    assert set(properties).isdisjoint({"user_id", "vehicle_id", "request_id", "runtime", "authentication", "catalog_item_id"})


@pytest.mark.asyncio
async def test_reward_read_tools_use_only_trusted_context_and_expire_before_read():
    runtime = _runtime("USER-001")
    voucher = SimpleNamespace(
        id="VOUCHER-1", redemption_id="REDEMPTION-1", catalog_code_snapshot="PARKING_15M",
        points_cost_snapshot=100, free_minutes_snapshot=15, validity_days_snapshot=30,
        status=ParkingVoucherStatus.ISSUED, issued_at=datetime.now(UTC), expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    summary = RewardSummary(available_points=15, pending_points=2, verified_contributions=1, daily_pending_points=2, daily_earned_points=15, daily_limit_points=100)
    catalog = [SimpleNamespace(id="CAT-1", code="ODD", name="Database reward", points_cost=123, free_minutes=44, validity_days=9, version=0)]
    with (
        patch("src.agents.tools.rewards.SlotObservationService.expire_pending", AsyncMock()) as expire_pending,
        patch("src.agents.tools.rewards.RewardService.get_summary", AsyncMock(return_value=summary)) as get_summary,
        patch("src.agents.tools.rewards.VoucherService.expire_stale", AsyncMock(return_value=0)) as expire_vouchers,
        patch("src.agents.tools.rewards.VoucherService.list_user_vouchers", AsyncMock(return_value=[voucher])) as get_vouchers,
        patch("src.agents.tools.rewards.RewardCatalogService.list_active", AsyncMock(return_value=catalog)),
    ):
        assert (await _invoke(get_reward_configuration, runtime))["ok"] is True
        summary_result = await _invoke(get_my_reward_summary, runtime)
        catalog_result = await _invoke(get_reward_catalog, runtime)
        vouchers_result = await _invoke(get_my_vouchers, runtime)
    expire_pending.assert_awaited_once()
    get_summary.assert_awaited_once_with("USER-001")
    expire_vouchers.assert_awaited_once_with("USER-001")
    get_vouchers.assert_awaited_once_with("USER-001")
    assert summary_result["data"]["available_points"] == 15
    assert catalog_result["data"] == [{"id": "CAT-1", "code": "ODD", "name": "Database reward", "points_cost": 123, "free_minutes": 44, "validity_days": 9, "version": 0}]
    assert vouchers_result["data"][0]["id"] == "VOUCHER-1"


def test_combined_agent_tools_are_unique_and_reward_tools_are_read_only():
    names = [tool.name for tool in AGENT_TOOLS]
    assert len(names) == len(set(names))
    assert {"get_reward_configuration", "get_my_reward_summary", "get_reward_catalog", "get_my_vouchers"}.issubset(names)
    assert {tool.name for tool in PARKING_TOOLS}.issubset(names)
    assert not any(any(word in name for word in ("redeem", "spend", "issue", "refund", "apply")) for name in names)
