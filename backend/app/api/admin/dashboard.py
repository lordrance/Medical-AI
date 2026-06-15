"""Research real-time audit dashboard endpoints.

These power the live `/admin` dashboard sections that researchers use to
audit incoming experimental data while the study is running. Each endpoint
returns a single aggregation; `/overview` bundles all of them for a single
client roundtrip.

Auth: every endpoint requires `X-Admin-Token` via `require_admin`, mirroring
the pattern in admin/summary.py and admin/export.py.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, rate_limit_admin
from app.core.security import require_admin
from app.middleware.metrics import get_recent_metrics
from app.services.analysis import (
    active_sessions,
    completion_timeseries,
    llm_call_stats,
    log_stats_overall,
    ui_event_frequency,
)

router = APIRouter(prefix="/api/admin/dashboard", tags=["admin-dashboard"])


@router.get("/llm-stats")
async def get_llm_stats(
    request: Request, db: AsyncSession = Depends(db_session),
    _rate: None = Depends(rate_limit_admin),
) -> dict:
    require_admin(request)
    return await llm_call_stats(db)


@router.get("/timeseries")
async def get_timeseries(
    request: Request,
    bucket: Literal["hour", "day"] = Query("hour"),
    window_hours: int = Query(168, ge=1, le=24 * 60),  # 1 hour to 60 days
    db: AsyncSession = Depends(db_session),
    _rate: None = Depends(rate_limit_admin),
) -> list[dict]:
    require_admin(request)
    return await completion_timeseries(db, bucket=bucket, window_hours=window_hours)


@router.get("/log-overall")
async def get_log_overall(
    request: Request, db: AsyncSession = Depends(db_session),
    _rate: None = Depends(rate_limit_admin),
) -> dict:
    require_admin(request)
    return await log_stats_overall(db)


@router.get("/ui-events")
async def get_ui_events(
    request: Request,
    by: Literal["condition", "case", "none"] = Query("condition"),
    db: AsyncSession = Depends(db_session),
    _rate: None = Depends(rate_limit_admin),
) -> list[dict]:
    require_admin(request)
    return await ui_event_frequency(db, by=by)


@router.get("/active-sessions")
async def get_active_sessions(
    request: Request, db: AsyncSession = Depends(db_session)
) -> list[dict]:
    require_admin(request)
    return await active_sessions(db)


@router.get("/health")
async def get_dashboard_health(
    request: Request,
    _rate: None = Depends(rate_limit_admin),
) -> dict:
    """Return request-level health metrics aggregated from the JSONL files.

    Fields:
    - ``errorRate``      — fraction of non-2xx responses in the last 60 minutes
    - ``p95LatencyMs``   — P95 request latency in ms
    - ``totalRequests``  — total requests in the last 60 minutes
    """
    require_admin(request)
    return get_recent_metrics(lookback_seconds=3600)


@router.get("/overview")
async def get_overview(
    request: Request, db: AsyncSession = Depends(db_session),
    _rate: None = Depends(rate_limit_admin),
) -> dict:
    """One-shot bundle of all dashboard data — preferred by the frontend
    polling loop so a single 401 / network error blocks the whole UI rather
    than five partial failures."""
    require_admin(request)
    return {
        "llmStats": await llm_call_stats(db),
        "timeseries": await completion_timeseries(db, bucket="hour"),
        "logOverall": await log_stats_overall(db),
        "uiEvents": await ui_event_frequency(db, by="none"),
        "activeSessions": await active_sessions(db),
    }
