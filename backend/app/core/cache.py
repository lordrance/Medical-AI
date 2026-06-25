"""Thread-safe in-memory cache for read-only seed data.

Cases, order templates, and survey configs never change at runtime
(they're loaded from JSON files at startup and seeded to the DB once).
Caching them avoids a DB round-trip on every participant request.

With 100 concurrent users, the ``/api/case/{id}`` endpoint is the
hottest path — each participant loads 8 formal cases + 1 practice case.
Without caching, that's 900 DB queries for case data alone.

Cache entries are stored in a plain dict; async access is single-threaded
per event-loop worker, and the dict is only written during app startup
(cold-fill) so no lock is needed.
"""

from __future__ import annotations

from typing import Any

_cache: dict[str, Any] = {}


def get(key: str) -> Any | None:
    """Return the cached value or None."""
    return _cache.get(key)


def set(key: str, value: Any) -> None:
    """Store a value in the cache."""
    _cache[key] = value


def invalidate(key: str | None = None) -> None:
    """Remove a key, or clear all (for testing)."""
    if key is not None:
        _cache.pop(key, None)
    else:
        _cache.clear()
