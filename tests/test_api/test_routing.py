from collections.abc import AsyncGenerator
from dataclasses import dataclass
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.api.main import REQUEST_ID_HEADER, create_app
from src.core.config import get_settings
from src.core.database import get_db_session
from src.core.db_models import Base, MapEdge
from src.core.seed import seed_if_missing


@dataclass(slots=True)
class RoutingApi:
    client: AsyncClient
    session_factory: async_sessionmaker[AsyncSession]


@pytest_asyncio.fixture
async def routing_api() -> AsyncGenerator[RoutingApi, None]:
    database_url = get_settings().database_url
    schema_name = f"test_routing_api_{uuid4().hex}"
    admin_engine = create_async_engine(database_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as connection:
        await connection.execute(CreateSchema(schema_name))

    engine = create_async_engine(
        database_url,
        connect_args={"server_settings": {"search_path": schema_name}},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await seed_if_missing(session)

    async def override_db_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    application = create_app()
    application.dependency_overrides[get_db_session] = override_db_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=application),
            base_url="http://test",
        ) as client:
            yield RoutingApi(client=client, session_factory=session_factory)
    finally:
        application.dependency_overrides.clear()
        await engine.dispose()
        async with admin_engine.connect() as connection:
            await connection.execute(DropSchema(schema_name, cascade=True))
        await admin_engine.dispose()


@pytest.mark.asyncio
async def test_shortest_route_returns_contract(routing_api: RoutingApi):
    response = await routing_api.client.post(
        "/api/v1/routes",
        json={
            "start_node_id": "F1-ENTRANCE",
            "destination_node_id": "F1-C01",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "start_node_id": "F1-ENTRANCE",
            "destination_node_id": "F1-C01",
            "path": ["F1-ENTRANCE", "F1-CP1", "F1-C-W", "F1-C01"],
            "distance_m": 41.0,
            "polyline": [[0.0, 50.0], [15.0, 50.0], [25.0, 70.0], [25.0, 74.0]],
        },
        "message": None,
    }


@pytest.mark.asyncio
async def test_route_node_not_found_returns_404_with_request_id(routing_api: RoutingApi):
    request_id = str(uuid4())

    response = await routing_api.client.post(
        "/api/v1/routes",
        headers={REQUEST_ID_HEADER: request_id},
        json={
            "start_node_id": "F1-UNKNOWN",
            "destination_node_id": "F1-C01",
        },
    )

    assert response.status_code == 404
    assert response.headers[REQUEST_ID_HEADER] == request_id
    assert response.json() == {
        "success": False,
        "error": {
            "code": "ROUTE_NODE_NOT_FOUND",
            "message": "Route node F1-UNKNOWN was not found",
            "request_id": request_id,
        },
    }


@pytest.mark.asyncio
async def test_route_not_found_returns_422_with_request_id(routing_api: RoutingApi):
    async with routing_api.session_factory() as session, session.begin():
        await session.execute(update(MapEdge).values(enabled=False))
    request_id = str(uuid4())

    response = await routing_api.client.post(
        "/api/v1/routes",
        headers={REQUEST_ID_HEADER: request_id},
        json={
            "start_node_id": "F1-ENTRANCE",
            "destination_node_id": "F1-C01",
        },
    )

    assert response.status_code == 422
    assert response.headers[REQUEST_ID_HEADER] == request_id
    assert response.json() == {
        "success": False,
        "error": {
            "code": "ROUTE_NOT_FOUND",
            "message": "No route exists from F1-ENTRANCE to F1-C01",
            "request_id": request_id,
        },
    }


@pytest.mark.asyncio
async def test_routing_registration_does_not_break_existing_routes(routing_api: RoutingApi):
    health = await routing_api.client.get("/health")
    parking = await routing_api.client.get("/api/v1/parking/status")
    openapi = await routing_api.client.get("/openapi.json")

    assert health.status_code == 200
    assert parking.status_code == 200
    assert openapi.status_code == 200
    paths = openapi.json()["paths"]
    assert "/api/v1/routes" in paths
    assert "/api/v1/simulator/reset" in paths
