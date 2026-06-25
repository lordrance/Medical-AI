from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_engine() -> AsyncEngine:
    settings = get_settings()
    url = settings.DATABASE_URL
    is_postgres = url.startswith("postgresql")
    engine_kwargs: dict = {
        "echo": False,
        "future": True,
        "pool_pre_ping": True,
    }
    if is_postgres:
        engine_kwargs.update({
            "pool_size": 10,
            "max_overflow": 10,
            "pool_recycle": 1800,
            "connect_args": {
                "timeout": 10,
                "command_timeout": 30,
                "keepalives_idle": 30,
            },
        })
    return create_async_engine(url, **engine_kwargs)


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an AsyncSession."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def reset_engine_for_tests() -> None:
    """Used by tests to dispose & rebuild engine after settings change."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
