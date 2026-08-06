"""
================================================================================
文件作用：全部配置项的定义 —— 数据库地址、管理员口令、AI 开关等
================================================================================

程序里凡是"因环境而异"的东西都在这里定义：本机开发连哪个库、生产连哪个库、
管理员口令是什么、要不要启用 AI。

★ 值从哪来：环境变量，或者项目根目录的 .env 文件。
  代码里写的只是「默认值」，生产环境会用真实的值覆盖掉。

★ 生产环境的实际取值在服务器的 ~/Medical-AI-NEW/.env 里（文件权限 600，
  只有属主能读）。本地开发看 backend/.env.example 了解有哪些变量可配。

★ 绝对不要把 .env 提交进 git —— 里面有管理员口令和数据库密码。
  项目的 .gitignore 已经排除了它，安全钩子也禁止读取它。

--------------------------------------------------------------------------------
本文件的代码块：
--------------------------------------------------------------------------------
  第 1 块  LLMProviderName   AI 供应商只能取哪几个值
  第 2 块  Settings          ★ 所有配置项的定义
  第 3 块  get_settings()    取配置（带缓存，全程只读一次）
================================================================================
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ── 第 1 块：AI 供应商的可选值 ─────────────────────────────────────────────
# Literal 表示"只能是这几个字符串之一"。
# 写成 str 的话，配置里打错字（比如写成 "deepsek"）程序照跑，
# 直到真正调用 AI 时才报一个莫名其妙的错。
# 用 Literal 的话，启动时就会因为值不合法而失败，问题立刻暴露。
LLMProviderName = Literal["disabled", "deepseek"]


# ── 第 2 块：所有配置项 ★ ──────────────────────────────────────────────────
class Settings(BaseSettings):
    """Runtime settings.

    Loaded from environment variables / .env file.

    中文：继承 BaseSettings 之后，Pydantic 会自动做三件事：
      1. 按下面每个字段的名字去找同名的环境变量
      2. 找不到就用这里写的默认值
      3. 检查类型对不对（比如 LLM_TIMEOUT_S 必须能转成小数）
    类型不对会在程序启动时就报错，而不是运行到一半才崩。
    """

    # env_file=".env" 表示除了环境变量，也去读项目根目录的 .env 文件。
    # extra="ignore" 表示 .env 里有多余的、这里没定义的变量就忽略掉，
    # 不报错——不然运维往 .env 里加个无关变量就会导致启动失败。
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- 应用基本信息 ---
    APP_NAME: str = "medical-ai-review-backend"
    # 运行环境。★ 如果生产环境的 /healthz 显示这里是 development，
    # 说明配置没注入进去，是个隐患。
    APP_ENV: Literal["development", "production", "test"] = "development"
    APP_VERSION: str = "0.2.0"

    # --- CORS：允许哪些网站的网页调用本 API ---
    # 生产环境前后端同域（都在 medraftlab.com 下，由 Caddy 分流），
    # 其实用不上 CORS。这个配置主要是给本地开发用的：
    # 那时前端跑在 :3000、后端跑在 :8000，属于跨域。
    #
    # default_factory 表示"默认值是一个新建的列表"。
    # ★ 不能直接写 = ["http://..."]，那样所有实例共用同一个列表对象，
    #   一个地方改了会影响所有地方——这是 Python 的经典陷阱。
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )

    # --- 数据库 ---
    # 默认是本地的 SQLite 文件（开发用，一个文件就是一个数据库）。
    # 生产环境由 docker-compose 注入成：
    #   postgresql+asyncpg://medai:密码@db:5432/medai
    # 前缀里的 asyncpg 是异步驱动的名字，必须有，否则连不上。
    DATABASE_URL: str = "sqlite+aiosqlite:///./dev.db"

    # --- 管理员口令 ---
    # ★ 这个默认值只在"忘了配置"时才会出现。
    # 生产环境由 .env 注入一个 64 位随机串。
    # core/security.py 会拿请求里带的令牌和它比对。
    ADMIN_TOKEN: str = "change-me-in-production"

    # --- AI 相关（V4 医生端完全不用，只有后台写研究总结时才用）---
    LLM_PROVIDER: LLMProviderName = "disabled"   # ★ 生产环境是 disabled
    DEEPSEEK_API_KEY: str | None = None          # 没配就自动降级成假数据模式
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    LLM_MAX_TOKENS: int = 1024                   # 单次生成最多多少 token
    LLM_TIMEOUT_S: float = 60.0                  # 超过 60 秒就放弃
    LLM_DRY_RUN: bool = False                    # True = 不真调 AI，返回假数据

    # @property 让下面这个函数用起来像个字段：写 settings.llm_enabled，
    # 不用写 settings.llm_enabled()。
    @property
    def llm_enabled(self) -> bool:
        """AI 是否启用。/healthz 接口会返回这个值。"""
        return self.LLM_PROVIDER != "disabled"


# ── 第 3 块：取配置 ────────────────────────────────────────────────────────
# @lru_cache(maxsize=1) 的意思是"结果只算一次，之后每次调用都返回同一个对象"。
#
# ★ 为什么要缓存：配置来自环境变量和文件，读一次就够了。全项目有十几处
#   调用 get_settings()，每个 HTTP 请求都可能调到，不缓存就是反复读文件。
#
# ★ 副作用（要知道）：改了 .env 必须重启后端才生效，因为缓存里还是旧值。
#   测试里如果要临时改配置，得先调 get_settings.cache_clear() 把缓存清掉
#   （见 tests/conftest.py）。
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """取全局唯一的配置对象。"""
    # type: ignore 是给类型检查工具看的：
    # Settings() 看起来没传任何参数，但 Pydantic 会自己从环境变量填充，
    # 类型检查工具不懂这个机制，会误报"缺少参数"，所以让它别管这行。
    return Settings()  # type: ignore[call-arg]
