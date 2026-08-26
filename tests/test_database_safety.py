from pathlib import Path

import pytest

from tests.database_safety import (
    ALLOWED_TEST_DATABASE_HOSTS,
    assert_safe_test_database_url,
    load_effective_database_url,
)


@pytest.mark.parametrize(
    "hostname",
    ["localhost", "127.0.0.1", "[::1]"],
)
def test_loopback_database_hosts_are_allowed(hostname: str) -> None:
    assert_safe_test_database_url(f"postgresql+asyncpg://test-user:test-password@{hostname}:5432/parksmart")


def test_repository_docker_database_hostname_is_allowed() -> None:
    assert ALLOWED_TEST_DATABASE_HOSTS == {
        "localhost",
        "127.0.0.1",
        "::1",
        "database",
    }
    assert_safe_test_database_url("postgresql+asyncpg://test-user:test-password@database:5432/parksmart")


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+asyncpg://user:password@db.project-ref.supabase.co:5432/postgres",
        ("postgresql+asyncpg://user:password@aws-0-region.pooler.supabase.com:6543/postgres"),
        "postgresql+asyncpg://user:password@database.example.com:5432/parksmart",
    ],
    ids=["supabase-direct", "supabase-pooler", "arbitrary-remote"],
)
def test_remote_database_hosts_are_rejected(database_url: str) -> None:
    with pytest.raises(RuntimeError, match="Unsafe pytest database target"):
        assert_safe_test_database_url(database_url)


def test_guard_error_does_not_expose_database_target_details() -> None:
    sensitive_values = [
        "sensitive-user",
        "sensitive-password",
        "private-project-ref",
        "sslmode",
    ]
    database_url = (
        "postgresql+asyncpg://sensitive-user:sensitive-password@"
        "db.private-project-ref.supabase.co:5432/postgres?sslmode=require"
    )

    with pytest.raises(RuntimeError) as exc_info:
        assert_safe_test_database_url(database_url)

    message = str(exc_info.value)
    assert all(value not in message for value in sensitive_values)
    assert "postgresql" not in message
    assert "://" not in message


def test_shell_database_url_override_is_effective(monkeypatch: pytest.MonkeyPatch) -> None:
    local_url = "postgresql+asyncpg://test-user:test-password@127.0.0.1:5432/parksmart"
    monkeypatch.setenv("DATABASE_URL", local_url)

    assert load_effective_database_url() == local_url


def test_root_conftest_enforces_guard_before_application_import() -> None:
    conftest = (Path(__file__).parent / "conftest.py").read_text(encoding="utf-8")

    assert conftest.index("enforce_safe_test_database()") < conftest.index("from src.main import app")
