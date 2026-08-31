"""Read-only reward adapters; identity always comes from the tool runtime."""

from langchain_core.tools import BaseTool, tool
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.tools.common import AgentToolRuntime, ToolResult, execute_tool, tool_success
from src.core.config import get_settings
from src.core.reward_redemption import RewardCatalogService
from src.models.schemas import RewardConfiguration


@tool
async def get_reward_configuration(runtime: AgentToolRuntime) -> ToolResult:
    """Get the authoritative ParkSmart Points earning rules and daily contribution cap."""

    async def operation(session: AsyncSession) -> ToolResult:
        settings = get_settings()
        return tool_success(
            RewardConfiguration(
                adjacent_observation_reward_points=settings.adjacent_observation_reward_points,
                wrong_parking_report_reward_points=settings.wrong_parking_report_reward_points,
                contribution_daily_points_limit=settings.contribution_daily_points_limit,
                redemption_enabled=settings.rewards_redemption_enabled,
            ).model_dump(mode="json")
        )

    return await execute_tool(runtime, "get_reward_configuration", operation)


@tool
async def get_reward_catalog(runtime: AgentToolRuntime) -> ToolResult:
    """List the active authoritative parking-time reward catalog. Never infer exchange rates."""

    async def operation(session: AsyncSession) -> ToolResult:
        return tool_success(
            [
                {
                    "id": item.id,
                    "code": item.code,
                    "name": item.name,
                    "points_cost": item.points_cost,
                    "free_minutes": item.free_minutes,
                    "validity_days": item.validity_days,
                    "version": item.version,
                }
                for item in await RewardCatalogService(session).list_active()
            ]
        )

    return await execute_tool(runtime, "get_reward_catalog", operation)


REWARD_TOOLS: tuple[BaseTool, ...] = (
    get_reward_configuration,
    get_reward_catalog,
)
__all__ = ["REWARD_TOOLS", "get_reward_configuration", "get_reward_catalog"]
