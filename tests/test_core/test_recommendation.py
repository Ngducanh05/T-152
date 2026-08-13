from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.core.config import get_settings
from src.core.db_models import (
    Base,
    MapEdge,
    MapNode,
    ParkingEvent,
    ParkingReservation,
    ParkingSlot,
)
from src.core.parking_state import ParkingStateService
from src.core.recommendation import RecommendationService
from src.core.reservation import ReservationService
from src.core.routing import RoutingService
from src.core.seed import seed_if_missing
from src.models.schemas import (
    ActorType,
    MapNodeType,
    ParkingEventType,
    RecommendationRequest,
    ReservationStatus,
    SlotStatus,
)


@pytest_asyncio.fixture
async def recommendation_session() -> AsyncGenerator[AsyncSession, None]:
    database_url = get_settings().database_url
    schema_name = f"test_recommendation_{uuid4().hex}"
    admin_engine = create_async_engine(database_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as connection:
        await connection.execute(CreateSchema(schema_name))

    engine = create_async_engine(
        database_url,
        connect_args={"server_settings": {"search_path": schema_name}},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as seed_session:
        await seed_if_missing(seed_session)

    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()
        async with admin_engine.connect() as connection:
            await connection.execute(DropSchema(schema_name, cascade=True))
        await admin_engine.dispose()


def _request(**overrides: object) -> RecommendationRequest:
    values: dict[str, object] = {
        "user_id": "USER-001",
        "start_node_id": "F1-ENTRANCE",
        "charging_required": False,
        "accessible_required": False,
        "near_elevator": False,
        "limit": 40,
    }
    values.update(overrides)
    return RecommendationRequest.model_validate(values)


def _service(session: AsyncSession) -> RecommendationService:
    return RecommendationService(
        session,
        ParkingStateService(session),
        RoutingService(session),
    )


@pytest.mark.asyncio
async def test_recommendation_returns_only_available(recommendation_session: AsyncSession):
    state = ParkingStateService(recommendation_session)
    await state.occupy_slot(
        "F1-A01",
        actor_type=ActorType.USER,
        actor_id="USER-001",
        vehicle_id="VEHICLE-001",
    )

    result = await _service(recommendation_session).recommend(_request())
    statuses = {slot.id: slot.status for slot in await state.list_slots()}

    assert result.recommendations
    assert all(statuses[item.slot_id] is SlotStatus.AVAILABLE for item in result.recommendations)


@pytest.mark.asyncio
async def test_ev_required_returns_only_charger_slots(recommendation_session: AsyncSession):
    result = await _service(recommendation_session).recommend(_request(charging_required=True))
    slots = {slot.id: slot for slot in await ParkingStateService(recommendation_session).list_slots()}

    assert len(result.recommendations) == 10
    assert all(slots[item.slot_id].has_charger for item in result.recommendations)


@pytest.mark.asyncio
async def test_reserved_never_recommended(recommendation_session: AsyncSession):
    state = ParkingStateService(recommendation_session)
    await state.reserve_slot(
        "F1-C01",
        "RESERVATION-001",
        user_id="USER-001",
        vehicle_id="VEHICLE-001",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    result = await _service(recommendation_session).recommend(_request(charging_required=True))

    assert "F1-C01" not in {item.slot_id for item in result.recommendations}


@pytest.mark.asyncio
async def test_expired_reservation_is_swept_before_recommendation(
    recommendation_session: AsyncSession,
):
    reserved_at = datetime(2026, 8, 13, 3, 0, tzinfo=UTC)
    recommendation_time = reserved_at + timedelta(minutes=6)
    state = ParkingStateService(recommendation_session)

    async with recommendation_session.begin():
        reservation = await ReservationService(
            recommendation_session,
            state,
        ).create_reservation(
            "USER-001",
            "VEHICLE-001",
            "F1-C01",
            now=reserved_at,
        )
        result = await RecommendationService(
            recommendation_session,
            state,
            RoutingService(recommendation_session),
            clock=lambda: recommendation_time,
        ).recommend(_request(charging_required=True))
        await RecommendationService(
            recommendation_session,
            state,
            RoutingService(recommendation_session),
            clock=lambda: recommendation_time,
        ).recommend(_request(charging_required=True))

    async with recommendation_session.begin():
        stored_reservation = await recommendation_session.get(
            ParkingReservation, reservation.id
        )
        slot = await recommendation_session.get(ParkingSlot, "F1-C01")
        expired_events = await recommendation_session.scalar(
            select(func.count())
            .select_from(ParkingEvent)
            .where(ParkingEvent.event_type == ParkingEventType.RESERVATION_EXPIRED)
        )

    assert slot is not None and slot.status is SlotStatus.AVAILABLE
    assert "F1-C01" in {candidate.slot_id for candidate in result.recommendations}
    assert stored_reservation is not None
    assert stored_reservation.status is ReservationStatus.EXPIRED
    assert expired_events == 1


@pytest.mark.asyncio
async def test_occupied_never_recommended(recommendation_session: AsyncSession):
    await ParkingStateService(recommendation_session).occupy_slot(
        "F1-D01",
        actor_type=ActorType.USER,
        actor_id="USER-001",
        vehicle_id="VEHICLE-001",
    )

    result = await _service(recommendation_session).recommend(_request(charging_required=True))

    assert "F1-D01" not in {item.slot_id for item in result.recommendations}


@pytest.mark.asyncio
async def test_accessible_required_empty_on_baseline(recommendation_session: AsyncSession):
    result = await _service(recommendation_session).recommend(_request(accessible_required=True))

    assert result.recommendations == []


@pytest.mark.asyncio
async def test_result_is_deterministic(recommendation_session: AsyncSession):
    service = _service(recommendation_session)

    results = [await service.recommend(_request(charging_required=True, near_elevator=True, limit=5)) for _ in range(3)]

    assert all(result == results[0] for result in results)
    assert all(result.model_dump(mode="json") == results[0].model_dump(mode="json") for result in results)


@pytest.mark.asyncio
async def test_tie_breaks_by_distance_then_slot_id(recommendation_session: AsyncSession):
    result = await _service(recommendation_session).recommend(_request())
    candidates = result.recommendations

    assert candidates == sorted(
        candidates,
        key=lambda item: (-item.score, item.distance_m, item.slot_id),
    )
    tie_groups: dict[tuple[float, float], list[str]] = {}
    for item in candidates:
        tie_groups.setdefault((item.score, item.distance_m), []).append(item.slot_id)
    assert any(len(slot_ids) > 1 for slot_ids in tie_groups.values())
    assert all(slot_ids == sorted(slot_ids) for slot_ids in tie_groups.values())


@pytest.mark.asyncio
async def test_limit(recommendation_session: AsyncSession):
    result = await _service(recommendation_session).recommend(_request(limit=3))

    assert len(result.recommendations) == 3


@pytest.mark.asyncio
async def test_no_matching_slot_returns_empty_result(recommendation_session: AsyncSession):
    result = await _service(recommendation_session).recommend(
        _request(charging_required=True, accessible_required=True)
    )

    assert result.recommendations == []
    assert result.parking_state_version == 0


@pytest.mark.asyncio
async def test_unreachable_candidate_is_excluded(recommendation_session: AsyncSession):
    await recommendation_session.execute(update(MapEdge).where(MapEdge.to_node == "F1-C01").values(enabled=False))

    result = await _service(recommendation_session).recommend(_request(charging_required=True))

    recommended_ids = {item.slot_id for item in result.recommendations}
    assert recommended_ids
    assert "F1-C01" not in recommended_ids


@pytest.mark.asyncio
async def test_recommendation_does_not_mutate_state(recommendation_session: AsyncSession):
    state = ParkingStateService(recommendation_session)
    before = {slot.id: (slot.status, slot.version, slot.occupied_by_vehicle_id) for slot in await state.list_slots()}
    before_events = await recommendation_session.scalar(select(func.count()).select_from(ParkingEvent))

    result = await _service(recommendation_session).recommend(_request(charging_required=True, near_elevator=True))

    after = {slot.id: (slot.status, slot.version, slot.occupied_by_vehicle_id) for slot in await state.list_slots()}
    after_events = await recommendation_session.scalar(select(func.count()).select_from(ParkingEvent))
    assert result.parking_state_version == sum(version for _, version, _ in before.values())
    assert after == before
    assert after_events == before_events
    assert not recommendation_session.dirty
    assert not recommendation_session.new


@pytest.mark.asyncio
async def test_recommendation_uses_one_graph_snapshot_and_three_sssp(
    recommendation_session: AsyncSession,
):
    routing = RoutingService(recommendation_session)
    service = RecommendationService(
        recommendation_session,
        ParkingStateService(recommendation_session),
        routing,
    )

    with (
        patch.object(routing, "load_graph", wraps=routing.load_graph) as load_graph,
        patch.object(
            routing,
            "shortest_distances",
            wraps=routing.shortest_distances,
        ) as shortest_distances,
        patch.object(routing, "get_route", wraps=routing.get_route) as get_route,
    ):
        result = await service.recommend(_request(charging_required=True, near_elevator=True))

    assert result.recommendations
    assert load_graph.await_count == 1
    assert shortest_distances.call_count == 3
    assert get_route.await_count == 0


@pytest.mark.asyncio
async def test_disconnected_edges_do_not_change_normalization(
    recommendation_session: AsyncSession,
):
    request = _request(charging_required=True, near_elevator=True, limit=10)
    before = await _service(recommendation_session).recommend(request)
    recommendation_session.add_all(
        [
            MapNode(
                id="F1-ISOLATED-A",
                floor_id="F1",
                type=MapNodeType.AISLE,
                x=1000,
                y=1000,
            ),
            MapNode(
                id="F1-ISOLATED-B",
                floor_id="F1",
                type=MapNodeType.AISLE,
                x=2000,
                y=2000,
            ),
        ]
    )
    await recommendation_session.flush()
    recommendation_session.add(
        MapEdge(
            from_node="F1-ISOLATED-A",
            to_node="F1-ISOLATED-B",
            distance_m=1_000_000,
            bidirectional=True,
            enabled=True,
        )
    )
    await recommendation_session.flush()

    after = await _service(recommendation_session).recommend(request)

    assert after == before
