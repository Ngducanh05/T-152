import pytest
from pydantic import ValidationError

from src.core.config import Settings


def test_wrong_parking_report_daily_limit_defaults_to_unlimited() -> None:
    assert Settings(_env_file=None).wrong_parking_report_daily_limit == 0


@pytest.mark.parametrize("value", [-1, 101])
def test_wrong_parking_report_daily_limit_enforces_bounds(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(wrong_parking_report_daily_limit=value)


def test_development_defaults_remain_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEBUG", raising=False)
    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.demo_mode is True
    assert settings.agent_enabled is True
    assert settings.speech_enabled is True
    assert settings.agent_daily_request_limit == 0
    assert settings.agent_max_steps == 8


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("agent_daily_request_limit", -1),
        ("agent_daily_request_limit", 1001),
        ("agent_max_steps", 0),
        ("agent_max_steps", 9),
    ],
)
def test_agent_quota_and_step_budget_bounds_are_enforced(
    field: str,
    value: int,
) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


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


def test_production_with_builtin_localhost_database_url_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

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


def test_production_missing_llm_api_key_is_rejected_when_agent_enabled() -> None:
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
            agent_enabled=True,
            speech_enabled=False,
        )

    assert "LLM_API_KEY is required" in str(exc_info.value)


def test_production_missing_llm_api_key_is_rejected_when_speech_enabled() -> None:
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
            agent_enabled=False,
            speech_enabled=True,
        )

    assert "LLM_API_KEY is required" in str(exc_info.value)


def test_production_without_llm_key_is_accepted_when_agent_and_speech_disabled() -> None:
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
        llm_api_key=None,
        agent_enabled=False,
        speech_enabled=False,
    )

    assert settings.llm_api_key is None


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


def test_observability_defaults_are_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("LANGSMITH_API_KEY", "LANGSMITH_PROJECT", "LANGSMITH_TRACING"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)

    assert settings.log_format == "text"
    assert settings.observability_enabled is False
    assert settings.otel_service_name == "parksmart-backend"
    assert settings.langsmith_project == "P152-production"
    assert settings.langsmith_tracing is False


@pytest.mark.parametrize("value", ["structured", "TEXT_JSON"])
def test_log_format_rejects_unsupported_values(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, log_format=value)


@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_sampling_ratio_enforces_bounds(value: float) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, otel_traces_sampler_arg=value)


def test_observability_disabled_allows_missing_otlp_configuration() -> None:
    settings = Settings(
        _env_file=None,
        observability_enabled=False,
        otel_exporter_otlp_endpoint=None,
        otel_exporter_otlp_headers=None,
    )

    assert settings.observability_enabled is False


def _production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "production",
        "debug": False,
        "demo_mode": False,
        "database_url": "postgresql+asyncpg://parksmart:parksmart@db.example.com:5432/app",
        "supabase_url": "https://example.supabase.co",
        "supabase_anon_key": "anon-test-key",
        "supabase_service_role_key": "service-role-test-key",
        "supabase_report_evidence_bucket": "wrong-parking-evidence",
        "llm_api_key": "llm-test-key",
        "langsmith_tracing": False,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize("field", ["otel_exporter_otlp_endpoint", "otel_exporter_otlp_headers"])
def test_production_observability_requires_otlp_endpoint_and_headers(field: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        _production_settings(observability_enabled=True, **{field: None})

    assert field.upper() in str(exc_info.value)


def test_production_observability_with_otlp_configuration_is_accepted() -> None:
    settings = _production_settings(
        observability_enabled=True,
        otel_exporter_otlp_endpoint="https://tenant.grafana.net/otlp",
        otel_exporter_otlp_headers="Authorization=Basic%20test",
    )

    assert settings.observability_enabled is True


def test_langchain_environment_aliases_populate_langsmith_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("LANGSMITH_API_KEY", "LANGSMITH_PROJECT", "LANGSMITH_TRACING"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANGCHAIN_API_KEY", "legacy-key")
    monkeypatch.setenv("LANGCHAIN_PROJECT", "legacy-project")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")

    settings = Settings(_env_file=None)

    assert settings.langsmith_api_key == "legacy-key"
    assert settings.langsmith_project == "legacy-project"
    assert settings.langsmith_tracing is True
