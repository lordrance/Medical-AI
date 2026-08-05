"""Thread-safe in-memory cache for read-only seed data.

Cases, order templates, and survey configs never change at runtime
(they're loaded from JSON files at startup and seeded to the DB once).
Caching them avoids a DB round-trip on every participant request.

With 100 concurrent users, the ``/api/case/{id}`` endpoint is the
hottest path — each participant loads 8 formal cases + 1 practice case.
Without caching, that's 900 DB queries for case data alone.

Cache entries are stored in a plain dict, filled lazily on first request
(cold-fill during request handling, not at startup). No lock is needed:
each Gunicorn worker runs a single-threaded asyncio loop, and the writes
are idempotent (every writer stores byte-identical read-only seed data).

Caveat: the cache is per-worker and never expires on its own. If seed data
changes (e.g. a case text hotfix + re-seed), restart the backend so all
workers drop their stale entries, or call ``invalidate()``. Tests must call
``invalidate()`` between cases (see conftest) because the module-level dict
outlives the per-test database.

──────────────────────────────────────────────────────────────────────────
★ 中文说明

这是一个极简的内存缓存，就是一个全局字典。缓存的是「题目内容」和
「题目顺序模板」这类**启动后就不会变**的只读数据。

为什么需要：100 个人同时答题时，`/api/case/{id}` 是最热的接口——
每人要调 9 次。不缓存的话光取题目就有 900 次数据库查询。

为什么不用加锁：每个 gunicorn worker 是单线程的 asyncio 事件循环，
不存在多线程同时写；而且就算两个请求都去填缓存，填进去的也是
一模一样的只读数据，覆盖谁都无所谓。

★ 注意事项（容易踩坑）：
  1. 缓存是**每个 worker 各存一份**的，4 个 worker 就有 4 份。
  2. 缓存**永不过期**。所以改了题目内容重新 seed 之后，必须
     重启后端，否则老 worker 还在发旧题目。
  3. 测试里每个用例之间必须调 invalidate()，因为这个字典是模块级的，
     活得比每个测试的临时数据库还久（见 tests/conftest.py）。
"""

from __future__ import annotations

from typing import Any

# 全局字典。键是自己约定的字符串，如 "case:case_01"、"templates"。
_cache: dict[str, Any] = {}


def get(key: str) -> Any | None:
    """Return the cached value or None.

    中文：取缓存。没有就返回 None，调用方据此决定要不要查数据库。
    """
    return _cache.get(key)


def set(key: str, value: Any) -> None:
    """Store a value in the cache.

    中文：存缓存。注意函数名和 Python 内置的 set() 撞了，
    所以调用方都写成 `from app.core.cache import set as cache_set`。
    """
    _cache[key] = value


def invalidate(key: str | None = None) -> None:
    """Remove a key, or clear all (for testing).

    中文：清缓存。不传参数 = 全清。改了题目内容后可以调它，
    但更保险的做法是直接重启后端（因为要清的是所有 worker）。
    """
    if key is not None:
        _cache.pop(key, None)
    else:
        _cache.clear()
