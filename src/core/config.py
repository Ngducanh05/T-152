from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ParkSmart AI"
    app_version: str = "0.1.0"
    app_env: str = "development"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://parksmart:parksmart@localhost:5432/parksmart"

    reservation_ttl_seconds: int = Field(default=300, gt=0)
    reservation_expiry_interval_seconds: float = Field(default=30.0, gt=0)
    reservation_expiry_batch_size: int = Field(default=100, gt=0, le=1000)
    idempotency_ttl_seconds: int = Field(default=86400, gt=0)
    adjacent_observation_reward_points: int = Field(default=10, ge=0)
    wrong_parking_report_reward_points: int = Field(default=20, ge=0)
    contribution_daily_points_limit: int = Field(default=100, ge=0)
    reward_business_timezone: str = "Asia/Ho_Chi_Minh"
    rewards_redemption_enabled: bool = False
    observation_verification_ttl_seconds: int = Field(default=1800, gt=0)
    report_reward_cooldown_seconds: int = Field(default=3600, ge=0)
    simulator_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "SIMULATOR_ENABLED",
            "ENABLE_SLOT_SIMULATOR",
        ),
    )
    demo_mode: bool = True
    agent_enabled: bool = True
    speech_enabled: bool = True
    next_public_api_base_url: str = "http://localhost:8000"

    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None
    supabase_report_evidence_bucket: str = "wrong-parking-evidence"
    auth_verification_cache_ttl_seconds: float = Field(default=15.0, gt=0, le=60)
    auth_verification_cache_max_entries: int = Field(default=2048, gt=0, le=10000)
    report_evidence_max_bytes: int = Field(default=5_000_000, gt=0, le=15_000_000)
    wrong_parking_report_daily_limit: int = Field(default=0, ge=0, le=100)

    llm_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "LLM_API_KEY",
            "OPENAI_API_KEY",
        ),
    )
    llm_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices(
            "LLM_MODEL",
            "OPENAI_MODEL",
            "MODEL_NAME",
        ),
    )
    llm_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        validation_alias=AliasChoices(
            "LLM_TEMPERATURE",
            "OPENAI_TEMPERATURE",
        ),
    )
    llm_timeout_seconds: float = Field(default=30.0, gt=0.0)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    speech_transcription_model: str = "gpt-4o-mini-transcribe"
    speech_max_audio_bytes: int = Field(default=2_000_000, gt=0, le=10_000_000)
    speech_timeout_seconds: float = Field(default=60.0, gt=0.0, le=120.0)
    speech_max_retries: int = Field(default=1, ge=0, le=2)
    agent_thread_ttl_seconds: float = Field(default=3600.0, gt=0.0)
    agent_daily_request_limit: int = Field(default=0, ge=0, le=1000)
    agent_max_steps: int = Field(default=8, ge=1, le=8)

    cors_origins: str = Field(
        default="http://localhost:3000",
        description="Comma-separated frontend origins",
    )
    log_level: str = "INFO"
    log_format: str = "text"
    observability_enabled: bool = False
    otel_service_name: str = "parksmart-backend"
    otel_service_version: str = "0.1.0"
    otel_exporter_otlp_protocol: str = "http/protobuf"
    otel_exporter_otlp_endpoint: str | None = None
    otel_exporter_otlp_headers: str | None = Field(default=None, repr=False)
    otel_traces_exporter: str = "otlp"
    otel_metrics_exporter: str = "otlp"
    otel_logs_exporter: str = "none"
    otel_traces_sampler: str = "parentbased_traceidratio"
    otel_traces_sampler_arg: float = Field(default=1.0, ge=0.0, le=1.0)
    otel_metric_export_interval: int = Field(default=60000, gt=0)
    service_version: str | None = None
    git_commit_sha: str | None = None

    langsmith_api_key: str | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"),
    )
    langsmith_project: str = Field(
        default="P152-production",
        validation_alias=AliasChoices("LANGSMITH_PROJECT", "LANGCHAIN_PROJECT"),
    )
    langsmith_tracing: bool = Field(
        default=False,
        validation_alias=AliasChoices("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"),
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator("database_url")
    @classmethod
    def database_url_must_use_asyncpg(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use postgresql+asyncpg://")
        return value

    @field_validator("log_format")
    @classmethod
    def log_format_must_be_supported(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"text", "json"}:
            raise ValueError("LOG_FORMAT must be text or json")
        return normalized

    @model_validator(mode="after")
    def production_configuration_must_fail_fast(self) -> "Settings":
        if self.app_env.strip().lower() not in {"production", "prod"}:
            return self

        failures: list[str] = []
        if self.debug:
            failures.append("DEBUG must be false")
        if self.demo_mode:
            failures.append("DEMO_MODE must be false")
        if self.database_url == "postgresql+asyncpg://parksmart:parksmart@localhost:5432/parksmart":
            failures.append("DATABASE_URL must not use the built-in local fallback")
        if not self.supabase_url:
            failures.append("SUPABASE_URL is required")
        if not self.supabase_anon_key:
            failures.append("SUPABASE_ANON_KEY is required")
        if not self.supabase_service_role_key:
            failures.append("SUPABASE_SERVICE_ROLE_KEY is required")
        if not self.supabase_report_evidence_bucket:
            failures.append("SUPABASE_REPORT_EVIDENCE_BUCKET is required")
        if (self.agent_enabled or self.speech_enabled) and not (self.llm_api_key or "").strip():
            failures.append("LLM_API_KEY is required")
        if self.observability_enabled:
            if not (self.otel_exporter_otlp_endpoint or "").strip():
                failures.append("OTEL_EXPORTER_OTLP_ENDPOINT is required")
            if not (self.otel_exporter_otlp_headers or "").strip():
                failures.append("OTEL_EXPORTER_OTLP_HEADERS is required")
            if self.otel_traces_sampler.lower() != "parentbased_traceidratio":
                failures.append("OTEL_TRACES_SAMPLER is unsupported")
            if self.otel_exporter_otlp_protocol.lower() != "http/protobuf":
                failures.append("OTEL_EXPORTER_OTLP_PROTOCOL is unsupported")
            if self.otel_traces_exporter.lower() != "otlp":
                failures.append("OTEL_TRACES_EXPORTER is unsupported")
        if self.langsmith_tracing and not (self.langsmith_api_key or "").strip():
            failures.append("LANGSMITH_API_KEY is required")

        if failures:
            raise ValueError(f"Unsafe production configuration: {'; '.join(failures)}")
        return self

    @property
    def environment(self) -> str:
        return self.app_env

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def model_name(self) -> str:
        """Compatibility alias used by the existing LLM factory."""
        return self.llm_model

    @property
    def openai_api_key(self) -> str | None:
        """Compatibility alias for the previous provider-specific name."""
        return self.llm_api_key

    @property
    def openai_model(self) -> str:
        """Compatibility alias for the previous provider-specific name."""
        return self.llm_model

    @property
    def openai_temperature(self) -> float:
        """Compatibility alias for the previous provider-specific name."""
        return self.llm_temperature

    @property
    def enable_slot_simulator(self) -> bool:
        """Compatibility alias for the previous simulator setting name."""
        return self.simulator_enabled


@lru_cache
def get_settings() -> Settings:
    return Settings()
