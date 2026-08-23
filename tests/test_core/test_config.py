import pytest
from pydantic import ValidationError

from src.core.config import Settings


def test_development_defaults_remain_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEBUG", raising=False)
    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.demo_mode is True


def test_production_with_demo_mode_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            app_env="production",
            debug=False,
            demo_mode=True,
            database_url="postgresql+asyncpg://parksmart:parksmart@db.example.com:5432/app",
            supabase_url="https://example.supabase.co",
            supabase_anon_key="anon-test-key",
            supabase_service_role_key="service-role-test-key",
            supabase_report_evidence_bucket="wrong-parking-evidence",
            llm_api_key="llm-test-key",
        )

    assert "DEMO_MODE must be false" in str(exc_info.value)


def test_production_with_builtin_localhost_database_url_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            app_env="prod",
            debug=False,
            demo_mode=False,
            supabase_url="https://example.supabase.co",
            supabase_anon_key="anon-test-key",
            supabase_service_role_key="service-role-test-key",
            supabase_report_evidence_bucket="wrong-parking-evidence",
            llm_api_key="llm-test-key",
        )

    assert "DATABASE_URL must not use the built-in local fallback" in str(exc_info.value)


def test_production_missing_supabase_auth_and_storage_settings_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            app_env="production",
            debug=False,
            demo_mode=False,
            database_url="postgresql+asyncpg://parksmart:parksmart@db.example.com:5432/app",
            supabase_url=None,
            supabase_anon_key=None,
            supabase_service_role_key=None,
            supabase_report_evidence_bucket="",
            llm_api_key="llm-test-key",
        )

    message = str(exc_info.value)
    assert "SUPABASE_URL is required" in message
    assert "SUPABASE_ANON_KEY is required" in message
    assert "SUPABASE_SERVICE_ROLE_KEY is required" in message
    assert "SUPABASE_REPORT_EVIDENCE_BUCKET is required" in message


def test_production_missing_llm_api_key_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            app_env="production",
            debug=False,
            demo_mode=False,
            database_url="postgresql+asyncpg://parksmart:parksmart@db.example.com:5432/app",
            supabase_url="https://example.supabase.co",
            supabase_anon_key="anon-test-key",
            supabase_service_role_key="service-role-test-key",
            supabase_report_evidence_bucket="wrong-parking-evidence",
            llm_api_key=None,
        )

    assert "LLM_API_KEY is required" in str(exc_info.value)


def test_valid_production_like_settings_are_accepted() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        debug=False,
        demo_mode=False,
        database_url="postgresql+asyncpg://parksmart:parksmart@db.example.com:5432/app",
        supabase_url="https://example.supabase.co",
        supabase_anon_key="anon-test-key",
        supabase_service_role_key="service-role-test-key",
        supabase_report_evidence_bucket="wrong-parking-evidence",
        llm_api_key="llm-test-key",
    )

    assert settings.app_env == "production"
    assert settings.demo_mode is False
