from __future__ import annotations

import structlog
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

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/summary")
async def get_summary(
    request: Request, db: AsyncSession = Depends(db_session)
) -> dict:
    require_admin(request)
    completion = await completion_stats(db)
    cm = await confusion_matrix(db)
    per_case = await per_case_stats(db)
    per_pt = await per_participant_stats(db)
    logger.info("admin_summary_loaded", total_participants=completion.get("totalParticipants"))
    return {
        "completion": completion,
        "confusionMatrix": cm,
        "perCase": per_case,
        "perParticipant": per_pt,
    }
