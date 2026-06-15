from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.db.base import utcnow
from app.db.models import Participant, PostSurvey, Session, UiEvent
from app.services.analysis import session_formal_performance

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["survey"])


class PreSurveyIn(BaseModel):
    sessionId: str
    answers: dict


class PostSurveyIn(BaseModel):
    sessionId: str
    payload: dict


@router.post("/api/pre-survey")
async def submit_pre_survey(
    body: PreSurveyIn, db: AsyncSession = Depends(db_session)
) -> dict:
    session = await db.get(Session, body.sessionId)
    if session is None:
        logger.warning("session_not_found", session_id=body.sessionId)
        raise HTTPException(404, "Unknown session")
    participant = await db.get(Participant, session.participant_id)
    if participant is None:
        logger.warning("participant_not_found", participant_id=session.participant_id)
        raise HTTPException(404, "Unknown participant")

    a = body.answers

    def _str(key: str) -> str | None:
        v = a.get(key)
        return v if isinstance(v, str) else None

    def _int(key: str) -> int | None:
        v = a.get(key)
        return v if isinstance(v, int) else None

    def _list(key: str) -> list | None:
        v = a.get(key)
        return v if isinstance(v, list) else None

    participant.specialty = _str("specialty")
    participant.training_level = _str("training_level")
    participant.years_practice = _int("years_practice")
    participant.weekly_message_volume = _str("weekly_message_volume")
    participant.prior_ai_use = _str("prior_ai_use")
    participant.ai_familiarity = _int("ai_familiarity")
    participant.ai_brands_used = _list("ai_brands_used")

    db.add(
        UiEvent(
            session_id=session.id,
            event_type="pre_survey_submitted",
            payload=a,
        )
    )
    await db.commit()
    logger.info("pre_survey_submitted", session_id=body.sessionId, participant_id=session.participant_id)
    return {"ok": True}


@router.post("/api/post-survey")
async def submit_post_survey(
    body: PostSurveyIn, db: AsyncSession = Depends(db_session)
) -> dict:
    session = await db.get(Session, body.sessionId)
    if session is None:
        logger.warning("session_not_found", session_id=body.sessionId)
        raise HTTPException(404, "Unknown session")

    db.add(
        PostSurvey(
            participant_id=session.participant_id,
            session_id=session.id,
            payload=body.payload,
        )
    )
    now = utcnow()
    session.status = "completed"
    session.ended_at = now

    participant = await db.get(Participant, session.participant_id)
    if participant is not None:
        participant.completed_flag = True
        participant.completed_at = now

    completion_code = f"AIDR-{session.participant_id[-8:].upper()}"
    performance = await session_formal_performance(db, session.id)
    await db.commit()
    logger.info(
        "post_survey_submitted",
        session_id=body.sessionId,
        participant_id=session.participant_id,
        completion_code=completion_code,
    )
    return {
        "ok": True,
        "completionCode": completion_code,
        "performance": performance,
    }
