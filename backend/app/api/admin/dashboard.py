"""Research real-time audit dashboard endpoints.

These power the live `/admin` dashboard sections that researchers use to
audit incoming experimental data while the study is running. Each endpoint
returns a single aggregation; `/overview` bundles all of them for a single
client roundtrip.

Auth: every endpoint requires `X-Admin-Token` via `require_admin`, mirroring
the pattern in admin/summary.py and admin/export.py.

★ 中文：管理后台看板的数据接口，共 6 个。

这些接口本身只是「薄薄一层壳」——真正的计算全在 services/analysis.py 里。
这样做的好处是：计算逻辑可以脱离 HTTP 单独测试，也能被导出功能复用。

★ 每个接口都必须调 require_admin(request)。漏了就等于把研究数据
公开给全世界。加新接口时千万别忘。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.core.security import require_admin
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
    request: Request, db: AsyncSession = Depends(db_session)
) -> dict:
    """AI 调用统计。V4 医生端不调 AI，所以这里通常是全零。"""
    require_admin(request)
    return await llm_call_stats(db)


@router.get("/timeseries")
async def get_timeseries(
    request: Request,
    bucket: Literal["hour", "day"] = Query("hour"),  # 按小时还是按天聚合
    # 看最近多久的数据。默认 168 小时 = 7 天。
    # ★ ge/le 限制了取值范围：防止有人传个超大数字让服务器扫全表卡死。
    window_hours: int = Query(168, ge=1, le=24 * 60),  # 1 hour to 60 days
    db: AsyncSession = Depends(db_session),
) -> list[dict]:
    """完成人数随时间的曲线。看板上那张折线图。"""
    require_admin(request)
    return await completion_timeseries(db, bucket=bucket, window_hours=window_hours)


@router.get("/log-overall")
async def get_log_overall(
    request: Request, db: AsyncSession = Depends(db_session)
) -> dict:
    """整体行为指标：平均用时、平均编辑距离、四种处理方式的分布等。"""
    require_admin(request)
    return await log_stats_overall(db)


@router.get("/ui-events")
async def get_ui_events(
    request: Request,
    by: Literal["condition", "case", "none"] = Query("condition"),  # 按什么维度分组
    db: AsyncSession = Depends(db_session),
) -> list[dict]:
    """行为埋点频次，看板上那张热力图的数据源。"""
    require_admin(request)
    return await ui_event_frequency(db, by=by)


@router.get("/active-sessions")
async def get_active_sessions(
    request: Request, db: AsyncSession = Depends(db_session)
) -> list[dict]:
    """★ 当前有谁正在答题。发放问卷期间最有用的一个接口——
    能实时看到有几个人在做、做到第几题了。"""
    require_admin(request)
    return await active_sessions(db)


@router.get("/overview")
async def get_overview(
    request: Request, db: AsyncSession = Depends(db_session)
) -> dict:
    """One-shot bundle of all dashboard data — preferred by the frontend
    polling loop so a single 401 / network error blocks the whole UI rather
    than five partial failures.

    ★ 中文：一次性返回上面 5 个接口的全部数据。

    为什么要有这个「打包接口」：后台会定时轮询刷新。如果分 5 个请求，
    token 过期时会看到 5 个错误提示、部分图表有数据部分没有，界面很乱。
    合成一个请求后，要么全成功要么全失败，前端只处理一种情况。
    """
    require_admin(request)
    return {
        "llmStats": await llm_call_stats(db),
        "timeseries": await completion_timeseries(db, bucket="hour"),
        "logOverall": await log_stats_overall(db),
        "uiEvents": await ui_event_frequency(db, by="none"),
        "activeSessions": await active_sessions(db),
    }
