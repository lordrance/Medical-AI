from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, rate_limit_admin
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
    request: Request,
    db: AsyncSession = Depends(db_session),
    _rate: None = Depends(rate_limit_admin),
) -> dict:
    require_admin(request)
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
