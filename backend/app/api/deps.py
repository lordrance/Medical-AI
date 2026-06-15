from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.rate_limiter import check_admin_rate, check_session_rate


async def db_session() -> AsyncIterator[AsyncSession]:
    async for s in get_db():
        yield s


DBSession = Depends(db_session)


# ---------------------------------------------------------------------------
# Rate-limit dependencies (V5). Attached to routes via `Depends(...)`.
# Using FastAPI Depends with Request means the limiter sees the real client
# IP even when the server sits behind Caddy.
# ---------------------------------------------------------------------------


def _client_ip(request: Request) -> str:
    """Best-effort client IP through proxy chain (Caddy → FastAPI)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def rate_limit_session(request: Request) -> None:
    key = _client_ip(request)
    if not check_session_rate(key):
        raise HTTPException(
            status_code=429,
            detail="Too many session requests. Please try again later.",
        )


async def rate_limit_admin(request: Request) -> None:
    key = _client_ip(request)
    if not check_admin_rate(key):
        raise HTTPException(
            status_code=429,
            detail="Too many admin requests. Please try again later.",
        )
