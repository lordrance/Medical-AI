from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.api.deps import db_session
from app.core.security import require_admin
from app.db.models import Session, LlmCall

router = APIRouter(prefix="/api/admin/dashboard", tags=["admin"])


@router.get("/health")
async def dashboard_health(
    request: Request, db: AsyncSession = Depends(db_session)
) -> dict:
    require_admin(request)

    # DB connectivity — simple query
    try:
        await db.execute(select(1))
        db_connected = True
    except Exception as exc:
        logger.warning("DashDB health — DB query failed: %s", exc)
        db_connected = False

    # LLM errors in last 24 hours
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    llm_err_count = 0
    try:
        result = await db.execute(
            select(func.count()).where(
                LlmCall.created_at >= since,
                LlmCall.error.isnot(None),
            )
        )
        llm_err_count = result.scalar() or 0
    except Exception as exc:
        logger.warning("DashDB health — LLM error count query failed: %s", exc)

    # Active sessions (status = "active" and started within last 2 hours)
    active_sessions = 0
    try:
        two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
        result = await db.execute(
            select(func.count()).where(
                Session.started_at >= two_hours_ago,
                Session.status == "active",
            )
        )
        active_sessions = result.scalar() or 0
    except Exception as exc:
        logger.warning("DashDB health — active sessions query failed: %s", exc)

    return {
        "dbConnected": db_connected,
        "serverTime": datetime.now(timezone.utc).isoformat(),
        "llmErrors24h": llm_err_count,
        "activeSessions": active_sessions,
    }
