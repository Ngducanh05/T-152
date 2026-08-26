import asyncio
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.core.config import Settings, get_settings
from src.core.db_models import Base
from src.core.errors import DomainError
from src.core.idempotency import IdempotencyService
from src.models.schemas import ErrorCode


@pytest_asyncio.fixture
async def idempotency_factory() -> AsyncGenerator[async_sessionmaker, None]:
    database_url = get_settings().database_url
    schema_name = f"test_idempotency_{uuid4().hex}"
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
    try:
        yield factory
    finally:
        await engine.dispose()
        async with admin_engine.connect() as connection:
            await connection.execute(DropSchema(schema_name, cascade=True))
        await admin_engine.dispose()


async def execute_once(
    factory: async_sessionmaker,
    *,
    key: str,
    payload: dict[str, object],
    executions: list[str],
) -> dict[str, object]:
    async with factory() as session, session.begin():
        service = IdempotencyService(session, settings=Settings(idempotency_ttl_seconds=60))
        claim = await service.claim(
            user_id="USER-001",
            operation="test_operation",
            key=key,
            payload=payload,
        )
        replay = service.replay(claim)
        if replay is not None:
            return replay
        executions.append(key)
        response = {"id": "RESULT-001", "value": payload["value"]}
        await service.complete(claim, response)
        return response


@pytest.mark.asyncio
async def test_sequential_duplicate_returns_original_result(
    idempotency_factory: async_sessionmaker,
) -> None:
    executions: list[str] = []
    first = await execute_once(
        idempotency_factory,
        key="retry-key",
        payload={"value": 1},
        executions=executions,
    )
    second = await execute_once(
        idempotency_factory,
        key="retry-key",
        payload={"value": 1},
        executions=executions,
    )

    assert first == second == {"id": "RESULT-001", "value": 1}
    assert executions == ["retry-key"]


@pytest.mark.asyncio
async def test_concurrent_duplicate_executes_business_operation_once(
    idempotency_factory: async_sessionmaker,
) -> None:
    executions: list[str] = []
    results = await asyncio.wait_for(
        asyncio.gather(
            execute_once(
                idempotency_factory,
                key="concurrent-key",
                payload={"value": 2},
                executions=executions,
            ),
            execute_once(
                idempotency_factory,
                key="concurrent-key",
                payload={"value": 2},
                executions=executions,
            ),
        ),
        timeout=5,
    )

    assert results[0] == results[1]
    assert executions == ["concurrent-key"]


@pytest.mark.asyncio
async def test_key_reuse_with_changed_payload_is_stable_conflict(
    idempotency_factory: async_sessionmaker,
) -> None:
    executions: list[str] = []
    await execute_once(
        idempotency_factory,
        key="changed-key",
        payload={"value": 1},
        executions=executions,
    )

    with pytest.raises(DomainError) as exc_info:
        await execute_once(
            idempotency_factory,
            key="changed-key",
            payload={"value": 2},
            executions=executions,
        )

    assert exc_info.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED
    assert executions == ["changed-key"]
