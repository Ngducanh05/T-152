from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage, ToolMessage

from src.api.main import REQUEST_ID_HEADER, create_app
from src.core.config import Settings


class FakeAgent:
    """Checkpoint-like fake Agent used without a model or network."""

    def __init__(self) -> None:
        self.threads: dict[str, list[Any]] = {}
        self.calls: list[dict[str, Any]] = []

    async def ainvoke(self, input_state, config, *, context):
        thread_id = config["configurable"]["thread_id"]
        history = self.threads.setdefault(thread_id, [])
        incoming = input_state["messages"]
        history.extend(incoming)
        user_text = incoming[-1].content
        self.calls.append(
            {
                "thread_id": thread_id,
                "context": context,
                "history_size": len(history),
            }
        )

        if "tìm" in user_text.lower():
            call_id = f"tool-{len(self.calls)}"
            history.extend(
                [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "recommend_parking_slot",
                                "args": {},
                                "id": call_id,
                                "type": "tool_call",
                            }
                        ],
                    ),
                    ToolMessage(
                        content=(
                            '{"ok": true, "data": {"recommendations": '
                            '[{"slot_id": "F1-C03"}]}}'
                        ),
                        tool_call_id=call_id,
                        name="recommend_parking_slot",
                    ),
                ]
            )
        answer = f"Lượt {sum(message.type == 'human' for message in history)} của thread."
        history.append(AIMessage(content=answer))
        return {
            "messages": list(history),
            "intent": "RECOMMEND_SLOT" if "tìm" in user_text.lower() else "CHAT",
            "selected_slot": "F1-C03" if "chọn" in user_text.lower() else "",
            "current_location": "F1-CP3",
            "recommended_slot_ids": (
                ["F1-C03"] if "tìm" in user_text.lower() else []
            ),
            "route": None,
        }


class SlowAgent:
    async def ainvoke(self, input_state, config, *, context):
        await asyncio.sleep(1)
        return {"messages": [AIMessage(content="too late")]}


class FailingAgent:
    async def ainvoke(self, input_state, config, *, context):
        raise RuntimeError("secret database exception")


class UnavailableAgent:
    async def ainvoke(self, input_state, config, *, context):
        return {
            "messages": [*input_state["messages"], AIMessage(content="internal fallback")],
            "error": "AGENT_TOOL_UNAVAILABLE: LLM_API_KEY is not configured",
        }


class StructuredRouteAgent:
    def __init__(self, *, ok: bool = True) -> None:
        self.ok = ok

    async def ainvoke(self, input_state, config, *, context):
        call_id = "route-call"
        tool_content = (
            {
                "ok": True,
                "data": {
                    "path": ["F1-CP3", "F1-D01"],
                    "distance_m": 10,
                    "polyline": [[85, 50], [58, 70]],
                },
            }
            if self.ok
            else {
                "ok": False,
                "error": {"code": "ROUTE_NOT_FOUND", "message": "No route."},
            }
        )
        return {
            "messages": [
                *input_state["messages"],
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_route",
                            "args": {"destination_node_id": "F1-D01"},
                            "id": call_id,
                            "type": "tool_call",
                        }
                    ],
                ),
                ToolMessage(
                    content=json.dumps(tool_content),
                    tool_call_id=call_id,
                    name="get_route",
                ),
                AIMessage(content="Đã xử lý tuyến đường."),
            ],
            "route": {
                "path": ["F1-CP3", "F1-D01"],
                "distance_m": 10,
                "polyline": [[85, 50], [58, 70]],
            },
            "tool_result": {"secret": "must-not-be-public"},
        }


class ConcurrentAgent:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def ainvoke(self, input_state, config, *, context):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.01)
            return {
                "messages": [
                    *input_state["messages"],
                    AIMessage(content="Đã xử lý."),
                ]
            }
        finally:
            self.active -= 1


@pytest_asyncio.fixture
async def agent_api():
    fake_agent = FakeAgent()
    application = create_app(
        Settings(_env_file=None, llm_api_key=None),
        agent_override=fake_agent,
    )
    async with application.router.lifespan_context(application):
        async with AsyncClient(
            transport=ASGITransport(app=application),
            base_url="http://test",
        ) as client:
            yield application, client, fake_agent


def _payload(
    *,
    thread_id: str = "THREAD-DEMO-001",
    user_id: str = "USER-001",
    message: str = "Tìm ô có sạc",
) -> dict[str, str]:
    return {
        "thread_id": thread_id,
        "user_id": user_id,
        "vehicle_id": "VEHICLE-001",
        "message": message,
    }


@pytest.mark.asyncio
async def test_happy_chat_response(agent_api):
    application, client, fake_agent = agent_api
    request_id = str(uuid4())

    response = await client.post(
        "/api/v1/agent/chat",
        headers={REQUEST_ID_HEADER: request_id},
        json=_payload(),
    )

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == request_id
    assert response.json() == {
        "success": True,
        "data": {
            "thread_id": "THREAD-DEMO-001",
            "message": "Lượt 1 của thread.",
            "intent": "RECOMMEND_SLOT",
            "selected_slot": None,
            "tool_names": ["recommend_parking_slot"],
            "current_location": "F1-CP3",
            "recommended_slot_ids": ["F1-C03"],
            "route": None,
        },
        "message": None,
    }
    call = fake_agent.calls[0]
    assert call["thread_id"] == "USER-001:THREAD-DEMO-001"
    assert call["context"].request_id == request_id
    assert call["context"].user_id == "USER-001"
    assert application.state.agent is fake_agent
    assert application.state.agent_checkpointer is not None


@pytest.mark.asyncio
async def test_two_turns_same_thread_keep_context(agent_api):
    _, client, fake_agent = agent_api

    first = await client.post("/api/v1/agent/chat", json=_payload(message="Xin chào"))
    second = await client.post("/api/v1/agent/chat", json=_payload(message="Tiếp tục"))

    assert first.json()["data"]["message"] == "Lượt 1 của thread."
    assert second.json()["data"]["message"] == "Lượt 2 của thread."
    assert [call["history_size"] for call in fake_agent.calls] == [1, 3]
    assert first.json()["data"]["recommended_slot_ids"] == []
    assert second.json()["data"]["recommended_slot_ids"] == []


@pytest.mark.asyncio
async def test_two_threads_do_not_share_state(agent_api):
    _, client, fake_agent = agent_api

    first = await client.post(
        "/api/v1/agent/chat",
        json=_payload(thread_id="THREAD-001", message="Xin chào"),
    )
    second = await client.post(
        "/api/v1/agent/chat",
        json=_payload(thread_id="THREAD-002", message="Xin chào"),
    )

    assert first.json()["data"]["message"] == "Lượt 1 của thread."
    assert second.json()["data"]["message"] == "Lượt 1 của thread."
    assert set(fake_agent.threads) == {"USER-001:THREAD-001", "USER-001:THREAD-002"}


@pytest.mark.asyncio
async def test_two_users_cannot_share_public_thread(agent_api):
    _, client, fake_agent = agent_api
    await client.post("/api/v1/agent/chat", json=_payload(user_id="USER-001"))

    response = await client.post(
        "/api/v1/agent/chat",
        json=_payload(user_id="USER-002"),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_TRANSITION"
    assert len(fake_agent.calls) == 1


@pytest.mark.asyncio
async def test_thread_lock_serializes_waiters_and_is_pruned_after_use():
    agent = ConcurrentAgent()
    application = create_app(
        Settings(_env_file=None, llm_api_key=None),
        agent_override=agent,
    )
    async with application.router.lifespan_context(application):
        async with AsyncClient(
            transport=ASGITransport(app=application),
            base_url="http://test",
        ) as client:
            responses = await asyncio.gather(
                client.post("/api/v1/agent/chat", json=_payload(message="Lượt một")),
                client.post("/api/v1/agent/chat", json=_payload(message="Lượt hai")),
            )

        assert [response.status_code for response in responses] == [200, 200]
        assert agent.max_active == 1
        assert application.state.agent_thread_locks == {}


@pytest.mark.asyncio
async def test_expired_thread_checkpoint_and_owner_are_reclaimed(agent_api):
    application, client, _ = agent_api
    first = await client.post(
        "/api/v1/agent/chat",
        json=_payload(user_id="USER-001", message="Xin chào"),
    )
    assert first.status_code == 200

    application.state.agent_thread_ttl_seconds = 0.01
    application.state.agent_thread_last_access["THREAD-DEMO-001"] -= 1
    reclaimed = await client.post(
        "/api/v1/agent/chat",
        json=_payload(user_id="USER-002", message="Xin chào"),
    )

    assert reclaimed.status_code == 200
    assert application.state.agent_thread_owners["THREAD-DEMO-001"] == "USER-002"
    assert application.state.agent_thread_locks == {}


@pytest.mark.asyncio
async def test_checkpoint_cleanup_does_not_block_a_different_thread(agent_api):
    application, client, _ = agent_api
    first = await client.post(
        "/api/v1/agent/chat",
        json=_payload(thread_id="THREAD-EXPIRED", message="Xin chào"),
    )
    assert first.status_code == 200
    application.state.agent_thread_ttl_seconds = 0.01
    application.state.agent_thread_last_access["THREAD-EXPIRED"] -= 1

    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()

    async def delayed_delete(thread_id: str) -> None:
        assert thread_id == "USER-001:THREAD-EXPIRED"
        cleanup_started.set()
        await release_cleanup.wait()

    with patch.object(
        application.state.agent_checkpointer,
        "adelete_thread",
        AsyncMock(side_effect=delayed_delete),
    ):
        response = await asyncio.wait_for(
            client.post(
                "/api/v1/agent/chat",
                json=_payload(thread_id="THREAD-OTHER", message="Xin chào"),
            ),
            timeout=0.2,
        )
        await asyncio.wait_for(cleanup_started.wait(), timeout=0.2)
        assert response.status_code == 200
        assert not release_cleanup.is_set()
        release_cleanup.set()


@pytest.mark.asyncio
async def test_same_thread_waits_until_checkpoint_cleanup_finishes(agent_api):
    application, client, _ = agent_api
    first = await client.post(
        "/api/v1/agent/chat",
        json=_payload(user_id="USER-001", message="Xin chào"),
    )
    assert first.status_code == 200
    application.state.agent_thread_ttl_seconds = 0.01
    application.state.agent_thread_last_access["THREAD-DEMO-001"] -= 1

    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()

    async def delayed_delete(thread_id: str) -> None:
        assert thread_id == "USER-001:THREAD-DEMO-001"
        cleanup_started.set()
        await release_cleanup.wait()

    with patch.object(
        application.state.agent_checkpointer,
        "adelete_thread",
        AsyncMock(side_effect=delayed_delete),
    ):
        request_task = asyncio.create_task(
            client.post(
                "/api/v1/agent/chat",
                json=_payload(user_id="USER-002", message="Xin chào"),
            )
        )
        await asyncio.wait_for(cleanup_started.wait(), timeout=0.2)
        await asyncio.sleep(0)
        assert not request_task.done()

        release_cleanup.set()
        response = await asyncio.wait_for(request_task, timeout=0.2)

    assert response.status_code == 200
    assert application.state.agent_thread_owners["THREAD-DEMO-001"] == "USER-002"


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["", "   "])
async def test_empty_message_is_rejected(agent_api, message):
    _, client, fake_agent = agent_api

    response = await client.post(
        "/api/v1/agent/chat",
        json=_payload(message=message),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert fake_agent.calls == []


async def _request_with_agent(agent, *, timeout: float = 30.0):
    application = create_app(
        Settings(_env_file=None, llm_api_key=None),
        agent_override=agent,
    )
    async with application.router.lifespan_context(application):
        application.state.agent_chat_timeout_seconds = timeout
        async with AsyncClient(
            transport=ASGITransport(app=application),
            base_url="http://test",
        ) as client:
            return await client.post("/api/v1/agent/chat", json=_payload())


@pytest.mark.asyncio
async def test_agent_timeout_returns_standard_503():
    response = await _request_with_agent(SlowAgent(), timeout=0.01)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AGENT_TOOL_UNAVAILABLE"
    assert response.json()["error"]["request_id"]
    assert "too late" not in response.text


@pytest.mark.asyncio
async def test_agent_exception_returns_standard_503_without_raw_error():
    response = await _request_with_agent(FailingAgent())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AGENT_TOOL_UNAVAILABLE"
    assert "secret database exception" not in response.text


@pytest.mark.asyncio
async def test_missing_api_key_state_returns_standard_503():
    response = await _request_with_agent(UnavailableAgent())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AGENT_TOOL_UNAVAILABLE"
    assert "LLM_API_KEY" not in response.text
    assert "internal fallback" not in response.text


@pytest.mark.asyncio
async def test_successful_current_turn_route_is_exposed_as_safe_structure():
    response = await _request_with_agent(StructuredRouteAgent())

    assert response.status_code == 200
    assert response.json()["data"]["route"] == {
        "path": ["F1-CP3", "F1-D01"],
        "distance_m": 10.0,
        "polyline": [[85.0, 50.0], [58.0, 70.0]],
    }
    assert "tool_result" not in response.json()["data"]
    assert "must-not-be-public" not in response.text


@pytest.mark.asyncio
async def test_failed_current_turn_route_does_not_expose_stale_state_route():
    response = await _request_with_agent(StructuredRouteAgent(ok=False))

    assert response.status_code == 200
    assert response.json()["data"]["route"] is None


@pytest.mark.asyncio
async def test_real_graph_missing_api_key_does_not_call_network_or_crash_app():
    application = create_app(Settings(_env_file=None, llm_api_key=None))
    missing_key_settings = SimpleNamespace(llm_api_key=None)
    with patch("src.services.llm.get_settings", return_value=missing_key_settings):
        async with application.router.lifespan_context(application):
            async with AsyncClient(
                transport=ASGITransport(app=application),
                base_url="http://test",
            ) as client:
                response = await client.post("/api/v1/agent/chat", json=_payload())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AGENT_TOOL_UNAVAILABLE"
    assert "LLM_API_KEY" not in response.text


@pytest.mark.asyncio
async def test_response_does_not_expose_internal_fields_or_secrets(agent_api):
    _, client, _ = agent_api

    response = await client.post("/api/v1/agent/chat", json=_payload())
    body = response.json()

    assert response.status_code == 200
    serialized = response.text.lower()
    assert "analysis" not in body["data"]
    assert "chain_of_thought" not in serialized
    assert "system_prompt" not in serialized
    assert "api_key" not in serialized
    assert "tool_calls" not in serialized


def test_agent_router_appears_in_openapi():
    application = create_app(Settings(_env_file=None, llm_api_key=None))
    operation = application.openapi()["paths"]["/api/v1/agent/chat"]["post"]

    assert operation["requestBody"]
    assert operation["responses"]["200"]
    response_schema = application.openapi()["components"]["schemas"]["ChatResponse"]
    assert "analysis" not in response_schema["properties"]
    assert {
        "current_location",
        "recommended_slot_ids",
        "route",
    } <= response_schema["properties"].keys()
