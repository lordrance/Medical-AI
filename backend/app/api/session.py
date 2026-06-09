from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.db.models import Case, OrderTemplate, Participant, Session, UiEvent
from app.services.randomization import pick_order_template_id

# V4: single-condition study. condition field retained on Participant /
# session_started UiEvent for schema continuity but always "single".
SINGLE_CONDITION: str = "single"

router = APIRouter(prefix="/api/session", tags=["session"])


class SessionCreatedResponse(BaseModel):
    sessionId: str
    participantId: str
    condition: str
    orderTemplateId: int
    caseOrder: list[str]
    practiceCaseId: str


@router.post("", response_model=SessionCreatedResponse)
async def create_session(db: AsyncSession = Depends(db_session)) -> SessionCreatedResponse:
    templates = (await db.execute(select(OrderTemplate))).scalars().all()
    if not templates:
        raise HTTPException(500, "No order templates seeded")

    template_id = pick_order_template_id([t.id for t in templates])
    template = next(t for t in templates if t.id == template_id)

    practice = (
        await db.execute(select(Case).where(Case.is_practice.is_(True)))
    ).scalars().first()
    if practice is None:
        raise HTTPException(500, "Practice case missing")

    condition = SINGLE_CONDITION

    participant = Participant(condition=condition, order_template_id=template_id)
    db.add(participant)
    await db.flush()

    session_row = Session(participant_id=participant.id)
    db.add(session_row)
    await db.flush()

    db.add(
        UiEvent(
            session_id=session_row.id,
            event_type="session_started",
            payload={"condition": condition, "orderTemplateId": template_id},
        )
    )
    await db.commit()

    return SessionCreatedResponse(
        sessionId=session_row.id,
        participantId=participant.id,
        condition=condition,
        orderTemplateId=template_id,
        caseOrder=list(template.order),
        practiceCaseId=practice.id,
    )
