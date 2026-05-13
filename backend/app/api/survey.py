from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.db.base import utcnow
from app.db.models import Participant, PostSurvey, Session, UiEvent
from app.schemas.post_survey_payload import PostSurveyV7Payload
from app.services.analysis import session_formal_performance

router = APIRouter(tags=["survey"])


class PreSurveyIn(BaseModel):
    sessionId: str
    answers: dict


class PostSurveyIn(BaseModel):
    sessionId: str
    payload: dict


def _str(a: dict, key: str) -> str | None:
    v = a.get(key)
    if isinstance(v, str) and v.strip():
        return v.strip()
    return None


def _int(a: dict, key: str) -> int | None:
    v = a.get(key)
    return v if isinstance(v, int) else None


@router.post("/api/pre-survey")
async def submit_pre_survey(
    body: PreSurveyIn, db: AsyncSession = Depends(db_session)
) -> dict:
    session = await db.get(Session, body.sessionId)
    if session is None:
        raise HTTPException(404, "Unknown session")
    participant = await db.get(Participant, session.participant_id)
    if participant is None:
        raise HTTPException(404, "Unknown participant")

    a = body.answers

    participant.pre_specialty = _str(a, "pre_specialty")
    participant.pre_training_level = _str(a, "pre_training_level")
    participant.pre_years_post_residency = _int(a, "pre_years_post_residency")
    participant.pre_weekly_msg_volume = _str(a, "pre_weekly_msg_volume")
    participant.pre_ai_drafting_familiarity = _int(a, "pre_ai_drafting_familiarity")

    db.add(
        UiEvent(
            session_id=session.id,
            event_type="pre_survey_submitted",
            payload=a,
        )
    )
    await db.commit()
    return {"ok": True}


@router.post("/api/post-survey")
async def submit_post_survey(
    body: PostSurveyIn, db: AsyncSession = Depends(db_session)
) -> dict:
    session = await db.get(Session, body.sessionId)
    if session is None:
        raise HTTPException(404, "Unknown session")

    try:
        validated = PostSurveyV7Payload.model_validate(body.payload)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()) from e

    db.add(
        PostSurvey(
            participant_id=session.participant_id,
            session_id=session.id,
            payload=validated.model_dump(),
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
    return {
        "ok": True,
        "completionCode": completion_code,
        "performance": performance,
    }
