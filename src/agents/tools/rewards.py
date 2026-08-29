"""Read-only reward adapters; identity always comes from the tool runtime."""

from langchain_core.tools import BaseTool, tool
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.tools.common import AgentToolRuntime, ToolResult, execute_tool, tool_success
from src.core.config import get_settings
from src.core.reward import RewardService
from src.core.reward_redemption import RewardCatalogService
from src.core.slot_observation import SlotObservationService
from src.core.voucher import VoucherService
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
            ).model_dump(mode="json")
        )

    return await execute_tool(runtime, "get_reward_configuration", operation)


@tool
async def get_my_reward_summary(runtime: AgentToolRuntime) -> ToolResult:
    """Get only the trusted current user's authoritative available and pending Points."""

    async def operation(session: AsyncSession) -> ToolResult:
        await SlotObservationService(session).expire_pending()
        return tool_success((await RewardService(session).get_summary(runtime.context.user_id)).model_dump(mode="json"))

    return await execute_tool(runtime, "get_my_reward_summary", operation, write=True)


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


@tool
async def get_my_vouchers(runtime: AgentToolRuntime) -> ToolResult:
    """List the trusted current user's own issued voucher wallet; this never spends Points."""

    async def operation(session: AsyncSession) -> ToolResult:
        service = VoucherService(session)
        await service.expire_stale(runtime.context.user_id)
        return tool_success(
            [
                {
                    "id": item.id,
                    "redemption_id": item.redemption_id,
                    "catalog_code_snapshot": item.catalog_code_snapshot,
                    "points_cost_snapshot": item.points_cost_snapshot,
                    "free_minutes_snapshot": item.free_minutes_snapshot,
                    "validity_days_snapshot": item.validity_days_snapshot,
                    "status": item.status.value,
                    "issued_at": item.issued_at.isoformat(),
                    "expires_at": item.expires_at.isoformat(),
                }
                for item in await service.list_user_vouchers(runtime.context.user_id)
            ]
        )

    return await execute_tool(runtime, "get_my_vouchers", operation, write=True)


REWARD_TOOLS: tuple[BaseTool, ...] = (
    get_reward_configuration,
    get_my_reward_summary,
    get_reward_catalog,
    get_my_vouchers,
)
__all__ = ["REWARD_TOOLS", "get_reward_configuration", "get_my_reward_summary", "get_reward_catalog", "get_my_vouchers"]
