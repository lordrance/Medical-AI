from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.db.models import Case, OrderTemplate, Participant, Session, UiEvent
from app.services.randomization import assign_condition, pick_order_template_id

logger = structlog.get_logger(__name__)

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
        logger.error("no_order_templates_seeded")
        raise HTTPException(500, "No order templates seeded")

    template_id = pick_order_template_id([t.id for t in templates])
    template = next(t for t in templates if t.id == template_id)

    practice = (
        await db.execute(select(Case).where(Case.is_practice.is_(True)))
    ).scalars().first()
    if practice is None:
        logger.error("practice_case_missing")
        raise HTTPException(500, "Practice case missing")

    condition = assign_condition()

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

    logger.info(
        "session_created",
        session_id=session_row.id,
        participant_id=participant.id,
        condition=condition,
        order_template_id=template_id,
    )

    return SessionCreatedResponse(
        sessionId=session_row.id,
        participantId=participant.id,
        condition=condition,
        orderTemplateId=template_id,
        caseOrder=list(template.order),
        practiceCaseId=practice.id,
    )
