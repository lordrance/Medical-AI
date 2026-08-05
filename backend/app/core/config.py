"""全部配置项。值来自环境变量或 .env 文件。

★ 生产环境的实际取值在服务器的 ~/Medical-AI-NEW/.env 里（权限 600）。
本地开发看 backend/.env.example 了解有哪些变量。
★ 绝不要把 .env 提交进 git —— 里面有管理员 token 和数据库密码。
"""

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
    # 默认是本地 SQLite 文件（开发用）。
    # 生产环境由 docker-compose 注入：postgresql+asyncpg://medai:密码@db:5432/medai
    DATABASE_URL: str = "sqlite+aiosqlite:///./dev.db"

    # Admin auth
    # ★ 这个默认值只在忘了配置时出现。生产环境由 .env 注入一个 64 位随机串。
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
    """取配置。★ lru_cache 让它只在第一次调用时真正读环境变量，
    之后每次都返回同一个对象——配置读一次就够了，不用每个请求都读文件。

    副作用：改了 .env 必须重启后端才生效。
    测试里要临时改配置得调 get_settings.cache_clear()（见 conftest.py）。
    """
    return Settings()  # type: ignore[call-arg]
