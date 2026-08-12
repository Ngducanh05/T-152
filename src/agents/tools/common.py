from __future__ import annotations

from langgraph.prebuilt import ToolRuntime

from src.agents.context import AgentRuntimeContext
from src.agents.state import AgentState

AgentToolRuntime = ToolRuntime[AgentRuntimeContext, AgentState]
"""Runtime type for future tools; the argument is hidden from model tool schemas."""
