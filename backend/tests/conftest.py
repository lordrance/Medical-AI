"""pytest 的公共配置。★ 这个文件不写测试，它准备测试运行的环境。

pytest 会自动加载名为 conftest.py 的文件，里面定义的 fixture（夹具）
可以被同目录下所有测试直接使用——测试函数只要把 fixture 名字写成参数，
pytest 就会自动把它准备好传进来。

这里做三件事：
  1. 在导入应用**之前**把数据库指向一个临时 SQLite 文件
  2. 每个测试用例前重建空数据库、清空缓存
  3. 提供一个能直接调接口的测试客户端
"""

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
#
# ★ 中文：这几行必须在 import app 之前执行，顺序不能调。
# 因为应用一被导入就会读取配置、建立数据库引擎；等导入完再设环境变量
# 就晚了——测试会连到你的开发库甚至生产库上去。
# 这也是文件下方那些 import 带 `# noqa: E402`（忽略「导入不在顶部」
# 这条规范检查）的原因。
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
    """每个测试用例跑之前，给它一个全新的空数据库。

    autouse=True 表示不用测试主动声明，自动对每个用例生效。
    这保证了测试之间完全隔离——上一个测试造的数据不会影响下一个。
    """
    # The in-memory seed-data cache is module-level and outlives the per-test
    # database, so clear it or entries from a prior test's DB leak into this one.
    #
    # ★ 中文：题目缓存是模块级的全局字典，活得比每个测试的数据库还久。
    # 不清的话，上个测试缓存的题目会「穿越」到下个测试——而那时数据库
    # 已经重建成空的了，于是出现「库里没有这道题但接口能返回」的诡异现象。
    cache.invalidate()
    await reset_engine_for_tests()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)    # 删掉所有表
        await conn.run_sync(Base.metadata.create_all)  # 按 models.py 重建
    yield  # ← 测试用例在这里执行
    await engine.dispose()  # 测试结束，关掉连接


@pytest.fixture
def admin_token() -> str:
    return "test-token"


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """能直接调接口的测试客户端。测试里写 `async def test_xxx(client)` 就能用。

    ★ ASGITransport 是关键：它让请求**不经过网络**，直接在内存里调进
    FastAPI 应用。所以测试不需要真的启动服务器、不占端口、速度极快
    （86 个测试 36 秒跑完），而且走的是和线上完全一样的中间件和路由。
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
