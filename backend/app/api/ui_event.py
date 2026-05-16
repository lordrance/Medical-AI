from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.db.models import UiEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ui-event", tags=["ui-event"])


class UiEventIn(BaseModel):
    sessionId: str
    casePresentationId: str | None = None
    eventType: str
    payload: dict[str, Any] | None = None
    clientTs: datetime | None = None


@router.post("")
async def submit_event(
    body: UiEventIn, db: AsyncSession = Depends(db_session)
) -> dict:
    # fire-and-forget semantics: never raise to client even on failure
    try:
        db.add(
            UiEvent(
                session_id=body.sessionId,
                case_presentation_id=body.casePresentationId,
                event_type=body.eventType,
                payload=body.payload,
                client_ts=body.clientTs,
            )
        )
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning(
            "ui_event persistence failed (silently dropped)",
            extra={
                "sessionId": body.sessionId,
                "casePresentationId": body.casePresentationId,
                "eventType": body.eventType,
            },
            exc_info=True,
        )
    return {"ok": True}
