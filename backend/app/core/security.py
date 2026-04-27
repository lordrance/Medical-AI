from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.core.config import get_settings


def require_admin(request: Request) -> None:
    """Validate admin token from `X-Admin-Token` header or `?token=` query.

    Raise 401 / 500 accordingly.
    """
    settings = get_settings()
    expected = settings.ADMIN_TOKEN
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ADMIN_TOKEN not configured on server",
        )

    token = request.headers.get("x-admin-token") or request.query_params.get("token")
    if token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
