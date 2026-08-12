from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from src.agents.context import AgentRuntimeContext
from src.agents.nodes.assistant import build_assistant_node
from src.agents.state import AgentState
from src.services.llm import get_llm


def build_graph(model: BaseChatModel | None = None):
    """Build the Phase 5 contract graph with an optional injected model.

    ``get_llm`` remains inside the node provider so building/importing the graph
    cannot construct a provider client or require credentials.
    """
    graph = StateGraph(AgentState, context_schema=AgentRuntimeContext)
    graph.add_node("assistant", build_assistant_node(lambda: get_llm(model)))
    graph.add_edge(START, "assistant")
    graph.add_edge("assistant", END)
    return graph.compile(name="parksmart-agent")


agent = build_graph()
