"""汇总统计接口 —— 后台首页那些数字的来源。

一个接口返回四块内容，都是写论文时最常看的：
  completion       完成率（多少人开始、多少人做完）
  confusionMatrix  ★ 混淆矩阵（标准答案 vs 医生实际选择）
  perCase          每道题的表现（哪道题最多人栽）
  perParticipant   每个人的表现（谁在敷衍）

导出 CSV 时也是把这一份 JSON 摊平（见 services/csv_export.py）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.core.security import require_admin
from app.services.analysis import (
    completion_stats,
    confusion_matrix,
    per_case_stats,
    per_participant_stats,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/summary")
async def get_summary(
    request: Request, db: AsyncSession = Depends(db_session)
) -> dict:
    """GET /api/admin/summary —— 研究数据汇总。"""
    require_admin(request)  # ★ 没这一行就等于把数据公开了
    completion = await completion_stats(db)
    cm = await confusion_matrix(db)
    per_case = await per_case_stats(db)
    per_pt = await per_participant_stats(db)
    return {
        "completion": completion,
        "confusionMatrix": cm,
        "perCase": per_case,
        "perParticipant": per_pt,
    }
