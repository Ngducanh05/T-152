"""LangGraph tool adapters over the ParkSmart Points reward ledger.

Neither tool lets the agent award or deduct points — that only happens
inside RewardService, triggered by verified observations/reports on the
REST side. get_my_reward_summary does perform one bookkeeping write: it
sweeps expired-but-unswept observations (mirroring the REST reward summary
endpoint) so the reported balance is accurate instead of stale.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool, tool
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.tools.common import AgentToolRuntime, ToolResult, execute_tool, tool_success
from src.core.config import get_settings
from src.core.reward import RewardService
from src.core.slot_observation import SlotObservationService
from src.models.schemas import RewardConfiguration


@tool
async def get_reward_configuration(runtime: AgentToolRuntime) -> ToolResult:
    """Get the official ParkSmart Points program rules: how many points each
    verified adjacent-slot observation and each verified wrong-parking report
    earns, and the shared daily point cap. Use this for general questions
    about how ParkSmart Points work, not for the user's personal balance."""

    async def operation(session: AsyncSession) -> ToolResult:
        settings = get_settings()
        configuration = RewardConfiguration(
            adjacent_observation_reward_points=settings.adjacent_observation_reward_points,
            wrong_parking_report_reward_points=settings.wrong_parking_report_reward_points,
            contribution_daily_points_limit=settings.contribution_daily_points_limit,
        )
        return tool_success(configuration.model_dump(mode="json"))

    return await execute_tool(runtime, "get_reward_configuration", operation)


@tool
async def get_my_reward_summary(runtime: AgentToolRuntime) -> ToolResult:
    """Get the trusted user's own ParkSmart Points balance: available points,
    pending points awaiting admin verification, verified contribution count,
    and today's earned/pending totals against the daily cap. Use this only
    for the current user's personal points, never another user's."""

    async def operation(session: AsyncSession) -> ToolResult:
        # Mirrors the REST /rewards/users/{user_id}/summary endpoint: an
        # observation's verification window can lapse before anything
        # reads it, so pending rewards must be expired before summing, or
        # pending_points/daily_pending_points overstate the balance.
        # available_points is unaffected — it only sums EARNED rewards.
        await SlotObservationService(session).expire_pending()
        summary = await RewardService(session).get_summary(runtime.context.user_id)
        return tool_success(summary.model_dump(mode="json"))

    return await execute_tool(runtime, "get_my_reward_summary", operation, write=True)


REWARD_TOOLS: tuple[BaseTool, ...] = (
    get_reward_configuration,
    get_my_reward_summary,
)

__all__ = [
    "REWARD_TOOLS",
    "get_my_reward_summary",
    "get_reward_configuration",
]
