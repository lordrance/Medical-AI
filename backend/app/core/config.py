from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProviderName = Literal["disabled", "deepseek"]


class Settings(BaseSettings):
    """Runtime settings.

    Loaded from environment variables / .env file.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "medical-ai-review-backend"
    APP_ENV: Literal["development", "production", "test"] = "development"
    APP_VERSION: str = "0.2.0"

    # CORS
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./dev.db"

    # Admin auth
    ADMIN_TOKEN: str = "change-me-in-production"

    # LLM
    LLM_PROVIDER: LLMProviderName = "disabled"
    DEEPSEEK_API_KEY: str | None = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    LLM_MAX_TOKENS: int = 1024
    LLM_TIMEOUT_S: float = 60.0
    LLM_DRY_RUN: bool = False

    @property
    def llm_enabled(self) -> bool:
        return self.LLM_PROVIDER != "disabled"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
