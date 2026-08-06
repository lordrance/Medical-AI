"""
================================================================================
文件作用：管理数据库连接 —— 连接池的配置都在这里
================================================================================

每个 HTTP 请求要读写数据库，都得先有一条"连接"。这个文件负责把连接管好。

★ 「连接池」是什么，为什么重要

  建立一条数据库连接是很慢的（要握手、认证，几十毫秒）。如果每个请求都
  新建一条、用完就扔，服务器大部分时间都花在建连接上了。

  所以程序启动时先开好一批连接放在"池子"里，请求来了borrow一条，
  用完还回去，下一个请求接着用。

  ★ 池子太小会出事：这正是之前医生反馈「网络异常」的一个原因——
    当时池子只有 5 条连接，第 6 个人来了就得排队等，等超时就报错。
    现在是每个进程 8 条常驻 + 高峰临时加 5 条。

--------------------------------------------------------------------------------
本文件的代码块（从上到下）：
--------------------------------------------------------------------------------
  第 1 块  _engine / _session_factory  两个全局变量（懒加载的缓存）
  第 2 块  _build_engine()             ★ 连接池的全部配置
  第 3 块  get_engine()                取引擎（第一次调用才真正创建）
  第 4 块  get_session_factory()       取会话工厂
  第 5 块  get_db()                    ★ 每个请求领一个会话，用完自动归还
  第 6 块  reset_engine_for_tests()    测试专用：推倒重来
================================================================================
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


# ── 第 1 块：两个全局变量 ──────────────────────────────────────────────────
# 一开始都是 None，第一次有人要用时才真正创建（这叫「懒加载」）。
# 创建好之后就一直存着，整个进程共用同一个——
# 引擎和连接池只该有一份，每个请求都新建一个池子就完全失去意义了。
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


# ── 第 2 块：连接池配置 ★ ──────────────────────────────────────────────────


def _build_engine() -> AsyncEngine:
    """建立数据库连接池。

    ★「连接池」是什么：程序不会每次查数据库都新建一条连接（那太慢），
    而是预先开好一批放着轮流用。池子太小 = 人一多就排队甚至超时，
    这正是之前医生反馈「网络异常」的原因之一（当时池子只有 5 条）。
    """
    settings = get_settings()
    url = settings.DATABASE_URL
    # 本地开发和测试用 SQLite（一个文件），生产用 Postgres。
    # 下面那些连接池参数 SQLite 不认，所以必须分开处理。
    is_postgres = url.startswith("postgresql")
    engine_kwargs: dict = {
        "echo": False,          # True 会把每条 SQL 打到日志里，调试时才开
        "future": True,
        # 每次从池子里拿连接前先 ping 一下。防止拿到一条已经被
        # 数据库/防火墙悄悄断掉的死连接，导致这个请求莫名其妙失败。
        "pool_pre_ping": True,
    }
    if is_postgres:
        # Per-worker pool tuned for gunicorn with 4 workers.
        # 4 workers × (8 + 5) = max 52 total Postgres connections.
        # Override via env: DB_POOL_SIZE, DB_MAX_OVERFLOW.
        #
        # 中文：生产环境跑 4 个 gunicorn worker（4 个独立进程），
        # 每个进程有自己的池子：常驻 8 条 + 高峰临时加 5 条。
        # 4 × 13 = 最多 52 条连接，Postgres 默认上限 100，留足余量。
        import os
        pool_size = int(os.getenv("DB_POOL_SIZE", "8"))
        max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "5"))
        engine_kwargs.update({
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            # 每条连接用满 30 分钟就换新的，避免长连接被中间设备静默切断。
            "pool_recycle": 1800,
            "connect_args": {
                "timeout": 10,          # 10 秒连不上数据库就放弃
                "command_timeout": 30,  # 单条 SQL 跑超过 30 秒就掐掉
                "server_settings": {
                    # 关掉 JIT：我们的查询都很小，JIT 编译的开销反而更大。
                    "jit": "off",
                    # 服务端也设一道 30 秒超时，双保险。
                    # 有了它，任何一条写歪的慢查询都不会把连接池卡死。
                    "statement_timeout": "30000",
                },
            },
        })
    return create_async_engine(url, **engine_kwargs)


# ── 第 3 块：取引擎 ────────────────────────────────────────────────────────
def get_engine() -> AsyncEngine:
    """取全局唯一的引擎，第一次调用时才创建（懒加载）。

    global 关键字表示"我要修改的是文件顶部那个全局变量，不是新建一个局部变量"。
    不写 global 的话，赋值只会造一个同名的局部变量，函数一结束就没了，
    下次进来 _engine 还是 None，每次都重新建池子。
    """
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


# ── 第 4 块：取会话工厂 ────────────────────────────────────────────────────
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """取「会话工厂」——每个请求都从它这里领一个数据库会话。

    "工厂"就是一个能不断造出新会话的东西。调一次 factory() 就得到一个新会话。
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            # ★ 必须为 False。默认 True 的话，commit 之后所有对象的属性会被
            # 标记为「过期」，下次访问会偷偷再查一次数据库；在 async 环境下
            # 这种隐式查询会直接报错。设为 False 也让 core/cache.py 缓存的
            # 对象在提交后依然可用。
            expire_on_commit=False,
            # 关掉自动 flush，改成代码里显式调用 db.flush()。
            # 这样什么时候写数据库是可控的，不会在查询时被意外触发。
            autoflush=False,
        )
    return _session_factory


# ── 第 5 块：每个请求领一个会话 ★ ─────────────────────────────────────────
async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an AsyncSession.

    中文：每个 HTTP 请求进来时，FastAPI 会调这个函数发一个数据库会话，
    请求处理完自动归还给连接池（`async with` 负责）。
    """
    factory = get_session_factory()
    # `async with` 保证无论中间发生什么，离开时都会把连接还回池子。
    # 不还的话，池子会被慢慢耗光，最后全站卡死——这类 bug 极难排查。
    async with factory() as session:
        try:
            yield session  # ← 请求处理期间停在这里
        except Exception:
            # 出任何错都先回滚。不回滚的话这条连接会带着失败的事务
            # 回到池子里，下一个请求拿到它就会莫名其妙地失败。
            await session.rollback()
            raise


# ── 第 6 块：测试专用，推倒重来 ───────────────────────────────────────────
async def reset_engine_for_tests() -> None:
    """Used by tests to dispose & rebuild engine after settings change.

    中文：测试专用。每个测试用例都要一个干净的数据库，
    所以先把旧引擎关掉、清空，下次调用 get_engine() 会重新建。
    """
    global _engine, _session_factory
    if _engine is not None:
        # dispose() 关掉池子里所有连接。不关的话上一个测试的连接会一直挂着，
        # 几十个测试跑下来会攒出一堆没人用的连接。
        await _engine.dispose()
    # 置回 None，下次调 get_engine() 就会重新创建，读取新的配置。
    _engine = None
    _session_factory = None
