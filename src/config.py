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

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()