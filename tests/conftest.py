import os
from unittest.mock import AsyncMock

# Most legacy API/core tests exercise the explicitly supported anonymous demo
# surface. Authentication tests override settings to production mode.
os.environ["DEMO_MODE"] = "true"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.database_safety import enforce_safe_test_database

enforce_safe_test_database()

from src.main import app  # noqa: E402  # Safety guard must run before app import.


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for testing API endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_llm():
    """Mock LLM to avoid calling OpenAI during tests.

    Usage in test:
        def test_something(mock_llm):
            # LLM calls will return mock response instead of hitting OpenAI
            ...
    """
    mock = AsyncMock()
    mock.ainvoke.return_value = AsyncMock(content="Mocked LLM response")
    return mock
