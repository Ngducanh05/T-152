from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ParkSmart AI"
    app_version: str = "0.1.0"
    app_env: str = "development"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://parksmart:parksmart@localhost:5432/parksmart"

    reservation_ttl_seconds: int = Field(default=300, gt=0)
    simulator_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "SIMULATOR_ENABLED",
            "ENABLE_SLOT_SIMULATOR",
        ),
    )
    demo_mode: bool = True
    next_public_api_base_url: str = "http://localhost:8000"

    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None

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

    cors_origins: str = Field(
        default="http://localhost:3000",
        description="Comma-separated frontend origins",
    )
    log_level: str = "INFO"

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
