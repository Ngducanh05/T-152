"""Fail-fast database target validation for the pytest process."""

from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

ALLOWED_TEST_DATABASE_HOSTS = frozenset(
    {
        "localhost",
        "127.0.0.1",
        "::1",
        "database",
    }
)
_SAFE_DATABASE_ERROR = (
    "Unsafe pytest database target. Set DATABASE_URL to an approved local or "
    "repository Docker test database before running pytest."
)


class _EffectiveDatabaseSettings(BaseSettings):
    """Resolve only DATABASE_URL without importing application settings."""

    database_url: str = "postgresql+asyncpg://parksmart:parksmart@localhost:5432/parksmart"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


def load_effective_database_url() -> str:
    """Load DATABASE_URL with shell environment taking precedence over .env."""

    return _EffectiveDatabaseSettings().database_url


def assert_safe_test_database_url(database_url: str) -> None:
    """Reject every database target not explicitly supported for repository tests."""

    try:
        parsed = urlsplit(database_url)
        hostname = parsed.hostname
    except (TypeError, ValueError):
        raise RuntimeError(_SAFE_DATABASE_ERROR) from None

    if parsed.scheme != "postgresql+asyncpg" or hostname is None or hostname.lower() not in ALLOWED_TEST_DATABASE_HOSTS:
        raise RuntimeError(_SAFE_DATABASE_ERROR)


def enforce_safe_test_database() -> None:
    """Validate the effective pytest target before application imports occur."""

    assert_safe_test_database_url(load_effective_database_url())


__all__ = [
    "ALLOWED_TEST_DATABASE_HOSTS",
    "assert_safe_test_database_url",
    "enforce_safe_test_database",
    "load_effective_database_url",
]
