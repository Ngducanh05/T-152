from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@dataclass(frozen=True, slots=True)
class AgentRuntimeContext:
    """Trusted identity, request metadata, and dependencies for one agent run.

    LangGraph injects this object into tools through ``ToolRuntime``. Keeping it
    outside ``AgentState`` prevents the model from supplying or changing identity
    fields and keeps database sessions out of checkpointed conversation state.
    """

    user_id: str
    vehicle_id: str | None
    request_id: str
    session_factory: async_sessionmaker[AsyncSession]
    current_location: str | None = None
