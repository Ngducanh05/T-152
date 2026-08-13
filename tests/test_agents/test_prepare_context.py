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
