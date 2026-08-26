from types import SimpleNamespace

from src.agents.context import AgentRuntimeContext
from src.agents.nodes.prepare_context import prepare_context


def test_confirmed_runtime_location_resolves_stale_missing_location():
    context = AgentRuntimeContext(
        user_id="USER-001",
        vehicle_id="VEHICLE-001",
        request_id="REQUEST-001",
        session_factory=None,  # type: ignore[arg-type]
        current_location="F1-ENTRANCE",
    )

    update = prepare_context(
        {"missing_fields": ["current_location"]},
        SimpleNamespace(context=context),  # type: ignore[arg-type]
    )

    assert update["current_location"] == "F1-ENTRANCE"
    assert update["missing_fields"] == []


def test_invocation_scoped_business_evidence_is_reset():
    context = AgentRuntimeContext(
        user_id="USER-001",
        vehicle_id="VEHICLE-001",
        request_id="REQUEST-002",
        session_factory=None,  # type: ignore[arg-type]
        current_location=None,
    )
    update = prepare_context(
        {
            "active_session_id": "STALE-SESSION",
            "active_reservation_id": "STALE-RESERVATION",
            "recommended_slot_ids": ["F2-C09"],
            "tool_result": {"ok": True},
        },
        SimpleNamespace(context=context),  # type: ignore[arg-type]
    )

    assert update["active_session_id"] == ""
    assert update["active_reservation_id"] == ""
    assert update["recommended_slot_ids"] == []
    assert update["tool_result"] == {}
