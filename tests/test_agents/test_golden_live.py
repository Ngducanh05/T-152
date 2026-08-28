"""Opt-in live-provider evaluation over the versioned ParkSmart golden set.

Run the complete dataset (partial selections are archived but never promoted):

    RUN_LIVE_LLM_EVAL=1 LLM_API_KEY=... uv run pytest \
        tests/test_agents/test_golden_live.py -m live_llm -q
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from eval.artifacts import GoldenRunRecorder, golden_case_payload
from eval.golden_cases import GOLDEN_CASES, GoldenCase
from eval.live_harness import (
    ToolCallLog,
    build_golden_tools,
    requested_tool_calls,
    score_case,
    tool_call_rounds,
)
from src.agents.context import AgentRuntimeContext
from src.agents.graph import build_graph
from src.core.config import get_settings
from src.services.llm import EFFECTIVE_LLM_TEMPERATURE

_EXPLICIT_LIVE_OPT_IN = os.getenv("RUN_LIVE_LLM_EVAL") == "1"
_LIVE_LLM_ENABLED = _EXPLICIT_LIVE_OPT_IN and bool(get_settings().llm_api_key)
_REASON = "Golden eval requires a key and explicit RUN_LIVE_LLM_EVAL=1 opt-in"


def _runtime(case: GoldenCase) -> AgentRuntimeContext:
    return AgentRuntimeContext(
        user_id="USER-001",
        vehicle_id="VEHICLE-001",
        request_id=f"GOLDEN-EVAL-{case.name}",
        session_factory=None,  # type: ignore[arg-type]
        current_location="F1-ENTRANCE",
    )


@pytest.fixture(scope="module")
def golden_recorder():
    settings = get_settings()
    recorder = GoldenRunRecorder(
        model=settings.llm_model,
        temperature=EFFECTIVE_LLM_TEMPERATURE,
        max_steps=settings.agent_max_steps,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    yield recorder
    archive, canonical = recorder.persist()
    target = canonical or archive
    print(f"Golden eval artifact: {target}")


@pytest.mark.live_llm
@pytest.mark.skipif(not _LIVE_LLM_ENABLED, reason=_REASON)
@pytest.mark.asyncio
@pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda case: case.name)
async def test_golden_case_live(case: GoldenCase, golden_recorder: GoldenRunRecorder):
    log = ToolCallLog()
    tools = build_golden_tools(log, scenario=case.scenario)
    settings = get_settings()
    graph = build_graph(
        tools=tools,
        max_steps=settings.agent_max_steps,
        checkpointer=InMemorySaver(),
    )
    config = {
        "configurable": {
            "thread_id": f"golden-{golden_recorder.run_id}-{case.name}",
        }
    }
    context = _runtime(case)

    # Latency is reported per graded turn, not per conversation: prior turns
    # only exist to build checkpoint state, so folding them into one number
    # would publish a two-request total under a single-request label and make
    # multi-turn cases dominate P95 by construction.
    result = None
    turn_durations: list[float] = []
    conversation_started = time.perf_counter()
    for turn_index, utterance in enumerate((*case.prior_turns, case.utterance)):
        log.current_turn_index = turn_index
        turn_started = time.perf_counter()
        async with asyncio.timeout(settings.llm_timeout_seconds):
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content=utterance)]},
                config=config,
                context=context,
            )
        turn_durations.append(time.perf_counter() - turn_started)
    conversation_duration_s = time.perf_counter() - conversation_started
    duration_s = turn_durations[-1]
    assert result is not None

    final_message = result["messages"][-1]
    final_text = final_message.content if isinstance(final_message.content, str) else ""
    rounds = tool_call_rounds(result["messages"])
    requests = requested_tool_calls(result["messages"])
    score = score_case(
        case,
        log.calls,
        final_text,
        call_rounds=rounds,
        requested_calls=requests,
    )

    golden_recorder.results.append(
        {
            "name": case.name,
            "category": case.category,
            "contract": golden_case_payload(case),
            "passed": score.passed,
            "reasons": list(score.reasons),
            "tool_compliant": score.tool_compliant,
            "response_compliant": score.response_compliant,
            "response_evaluable": score.response_evaluable,
            "refusal_compliant": score.refusal_compliant,
            "unauthorized_write": score.unauthorized_write,
            "forbidden_read": score.forbidden_read,
            "duration_s": round(duration_s, 3),
            "turn_durations_s": [round(value, 3) for value in turn_durations],
            "conversation_duration_s": round(conversation_duration_s, 3),
            "graded_turn_index": len(turn_durations) - 1,
            "executed_calls": log.as_list(),
            "requested_calls": [item.as_dict() for item in requests],
            "tool_call_rounds": [list(names) for names in rounds],
            "final_text": final_text,
        }
    )

    assert score.passed, f"{case.name} failed: {'; '.join(score.reasons)}"
