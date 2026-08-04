from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ParkSmart AI"
    app_env: str = "development"
    debug: bool = False

    database_url: str = (
        "postgresql+asyncpg://parksmart:parksmart@localhost:5432/parksmart"
    )

    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    enable_slot_simulator: bool = True

    cors_origins: str = Field(
        default="http://localhost:3000",
        description="Comma-separated frontend origins",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

<<<<<<< HEAD
    # App
    app_name: str = "ParkSmart AI"
    app_env: Literal["development", "production", "test"] = "development"
    debug: bool = False
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:3000"

    # LLM
    openai_api_key: str = ""
    model_name: str = "gpt-4o-mini"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    # Database
    database_url: str = (
        "postgresql+asyncpg://parksmart:parksmart@localhost:5432/parksmart"
    )

    # Supabase Auth. The service role key is backend-only and must never be
    # sent to the frontend or committed to the repository.
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None

    # Vector Store
    chroma_persist_dir: str = "./data/chroma"
=======
    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]
>>>>>>> 7bfdef8664e5fb388c432168789d837cc6c3dcb0


@lru_cache
def get_settings() -> Settings:
    return Settings()