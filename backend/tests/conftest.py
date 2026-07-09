from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Configure DB **before** importing the app.
# - 默认：临时 SQLite（本地 / CI 不连 PG 时）。
# - CI 或本地若已导出 `DATABASE_URL`（如 postgresql+asyncpg://…），则使用该库（双跑 PG 用）。
if "DATABASE_URL" not in os.environ:
    _tmp_dir = tempfile.mkdtemp(prefix="medai-test-")
    _db_path = os.path.join(_tmp_dir, "test.db")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_db_path}"

os.environ.setdefault("ADMIN_TOKEN", "test-token")
os.environ.setdefault("LLM_PROVIDER", "disabled")

from app.core import cache  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_engine, reset_engine_for_tests  # noqa: E402
from app.main import app  # noqa: E402

get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest_asyncio.fixture(autouse=True)
async def _setup_db() -> AsyncIterator[None]:
    # The in-memory seed-data cache is module-level and outlives the per-test
    # database, so clear it or entries from a prior test's DB leak into this one.
    cache.invalidate()
    await reset_engine_for_tests()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture
def admin_token() -> str:
    return "test-token"


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
