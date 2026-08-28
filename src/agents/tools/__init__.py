from langchain_core.tools import BaseTool

from src.agents.tools.common import AgentToolRuntime
from src.agents.tools.parking import (
    PARKING_TOOLS,
    cancel_reservation,
    complete_parking_session,
    confirm_parking,
    find_parked_vehicle,
    get_parking_slot_status,
    get_parking_status,
    get_route,
    recommend_parking_slot,
    reserve_parking_slot,
    set_user_location,
)
from src.agents.tools.rewards import (
    REWARD_TOOLS,
    get_my_reward_summary,
    get_reward_configuration,
)

AGENT_TOOLS: tuple[BaseTool, ...] = PARKING_TOOLS + REWARD_TOOLS

__all__ = [
    "AGENT_TOOLS",
    "AgentToolRuntime",
    "PARKING_TOOLS",
    "REWARD_TOOLS",
    "cancel_reservation",
    "complete_parking_session",
    "confirm_parking",
    "find_parked_vehicle",
    "get_my_reward_summary",
    "get_parking_slot_status",
    "get_parking_status",
    "get_reward_configuration",
    "get_route",
    "recommend_parking_slot",
    "reserve_parking_slot",
    "set_user_location",
]
