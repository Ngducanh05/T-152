from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.core.config import get_settings
from src.core.db_models import Base, MapEdge, MapNode
from src.core.routing import RoutingError, RoutingService
from src.core.seed import seed_if_missing
from src.models.schemas import ErrorCode


@pytest_asyncio.fixture
async def routing_session() -> AsyncGenerator[AsyncSession, None]:
    database_url = get_settings().database_url
    schema_name = f"test_routing_{uuid4().hex}"
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


@pytest.mark.asyncio
async def test_shortest_path_entrance_to_c01(routing_session: AsyncSession):
    route = await RoutingService(routing_session).get_route("F1-ENTRANCE", "F1-C01")

    assert route.path == ["F1-ENTRANCE", "F1-CP1", "F1-C-W", "F1-C01"]
    assert route.distance_m == 41


@pytest.mark.asyncio
async def test_shortest_path_entrance_to_d01(routing_session: AsyncSession):
    route = await RoutingService(routing_session).get_route("F1-ENTRANCE", "F1-D01")

    assert route.path == [
        "F1-ENTRANCE",
        "F1-CP1",
        "F1-CP2",
        "F1-D-W",
        "F1-D01",
    ]
    assert route.distance_m == 76


@pytest.mark.asyncio
async def test_route_to_every_slot(routing_session: AsyncSession):
    service = RoutingService(routing_session)

    for zone_id in "ABCD":
        for slot_number in range(1, 11):
            slot_id = f"F1-{zone_id}{slot_number:02d}"
            route = await service.get_route("F1-ENTRANCE", slot_id)
            assert route.path[0] == "F1-ENTRANCE"
            assert route.path[-1] == slot_id
            assert slot_id not in route.path[:-1]


@pytest.mark.asyncio
async def test_same_start_and_destination(routing_session: AsyncSession):
    route = await RoutingService(routing_session).get_route("F1-CP2", "F1-CP2")

    assert route.path == ["F1-CP2"]
    assert route.distance_m == 0
    assert route.polyline == [(50.0, 50.0)]


@pytest.mark.asyncio
async def test_result_is_deterministic(routing_session: AsyncSession):
    service = RoutingService(routing_session)

    results = [await service.get_route("F1-ELEVATOR", "F1-CP2") for _ in range(5)]

    assert all(result == results[0] for result in results)
    assert results[0].path == ["F1-ELEVATOR", "F1-C-E", "F1-CP2"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("start_node_id", "destination_node_id"),
    [("F1-UNKNOWN", "F1-C01"), ("F1-ENTRANCE", "F1-UNKNOWN")],
)
async def test_invalid_start_or_destination(
    routing_session: AsyncSession,
    start_node_id: str,
    destination_node_id: str,
):
    with pytest.raises(RoutingError) as error:
        await RoutingService(routing_session).get_route(
            start_node_id,
            destination_node_id,
        )

    assert error.value.code is ErrorCode.ROUTE_NODE_NOT_FOUND


@pytest.mark.asyncio
async def test_no_route_when_edges_disabled(routing_session: AsyncSession):
    await routing_session.execute(update(MapEdge).values(enabled=False))

    with pytest.raises(RoutingError) as error:
        await RoutingService(routing_session).get_route("F1-ENTRANCE", "F1-C01")

    assert error.value.code is ErrorCode.ROUTE_NOT_FOUND


@pytest.mark.asyncio
async def test_polyline_matches_path(routing_session: AsyncSession):
    route = await RoutingService(routing_session).get_route("F1-ENTRANCE", "F1-C01")
    nodes = {node.id: node for node in await routing_session.scalars(select(MapNode))}

    assert route.polyline == [(nodes[node_id].x, nodes[node_id].y) for node_id in route.path]


@pytest.mark.asyncio
async def test_bidirectional_edge(routing_session: AsyncSession):
    await routing_session.execute(update(MapEdge).values(enabled=False))
    edge = await routing_session.get(MapEdge, ("F1-ENTRANCE", "F1-CP1"))
    assert edge is not None
    edge.enabled = True
    edge.bidirectional = True
    await routing_session.flush()

    forward = await RoutingService(routing_session).get_route("F1-ENTRANCE", "F1-CP1")
    reverse = await RoutingService(routing_session).get_route("F1-CP1", "F1-ENTRANCE")

    assert forward.distance_m == reverse.distance_m == 15
    assert forward.path == ["F1-ENTRANCE", "F1-CP1"]
    assert reverse.path == ["F1-CP1", "F1-ENTRANCE"]

    edge.bidirectional = False
    await routing_session.flush()
    with pytest.raises(RoutingError) as error:
        await RoutingService(routing_session).get_route("F1-CP1", "F1-ENTRANCE")
    assert error.value.code is ErrorCode.ROUTE_NOT_FOUND


@pytest.mark.asyncio
async def test_sssp_reuses_loaded_graph(routing_session: AsyncSession):
    service = RoutingService(routing_session)
    graph = await service.load_graph()

    from_entrance = service.shortest_distances(graph, "F1-ENTRANCE")
    to_exit = service.shortest_distances(graph, "F1-EXIT", reverse=True)
    route = service.route_on_graph(graph, "F1-ENTRANCE", "F1-C01")

    assert from_entrance["F1-C01"] == route.distance_m
    assert to_exit["F1-C01"] > 0
