from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.db.models import Action, Case, CasePresentation, Participant, Session
from app.schemas.case import CasePayload, CaseResponse

router = APIRouter(prefix="/api/case", tags=["case"])


# V4 design constraint: the AI draft shown to every participant for a given
# case must be byte-identical, otherwise the AI text becomes an uncontrolled
# experimental variable. So we never invoke the LLM during participant case
# rendering — we return the seeded `ai_draft` verbatim. The V3 live-LLM
# implementation (provider invocation, prompt rendering, llm_calls audit
# rows for case_draft / risk_tip) lives in git history at the V3 tag if a
# future revision needs to restore it.
#
# The guardrail UI is also intentionally not rendered (single-condition
# study), so factsUsed / riskCue / checklist seed data is exported as
# research metadata but not surfaced to participants.


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: str,
    sessionId: str = Query(...),
    db: AsyncSession = Depends(db_session),
) -> CaseResponse:
    session = await db.get(Session, sessionId)
    if session is None:
        raise HTTPException(404, "Unknown session")
    participant = await db.get(Participant, session.participant_id)
    if participant is None:
        raise HTTPException(404, "Unknown participant")

    # Cases are read-only seed data — serve from memory when cached.
    from app.core.cache import get as cache_get, set as cache_set

    cache_key = f"case:{case_id}"
    cached = cache_get(cache_key)
    if cached is not None:
        return CaseResponse(case=cached)

    case = await db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")

    payload = CasePayload(
        id=case.id,
        isPractice=case.is_practice,
        riskLevel=case.risk_level,
        patientMessage=case.patient_message,
        chartSnapshot=case.chart_snapshot,
        aiDraft=case.ai_draft,
        guardrail=None,
    )
    cache_set(cache_key, payload)
    return CaseResponse(case=payload)


class CaseOpenIn(BaseModel):
    sessionId: str
    caseId: str
    orderIndex: int = Field(..., ge=-1)


class CaseOpenOut(BaseModel):
    casePresentationId: str


@router.post("/open", response_model=CaseOpenOut)
async def open_case(
    body: CaseOpenIn,
    db: AsyncSession = Depends(db_session),
) -> CaseOpenOut:
    """Create or return an in-progress CasePresentation for UI event correlation."""
    session = await db.get(Session, body.sessionId)
    if session is None:
        raise HTTPException(404, "Unknown session")
    case = await db.get(Case, body.caseId)
    if case is None:
        raise HTTPException(404, "Case not found")

    reuse_stmt = (
        select(CasePresentation)
        .outerjoin(Action, Action.case_presentation_id == CasePresentation.id)
        .where(
            CasePresentation.session_id == session.id,
            CasePresentation.case_id == case.id,
            Action.id.is_(None),
        )
        .order_by(CasePresentation.started_at.asc())
        .limit(1)
    )
    existing = (await db.execute(reuse_stmt)).scalars().first()
    if existing is not None:
        existing.order_index = body.orderIndex
        await db.commit()
        return CaseOpenOut(casePresentationId=existing.id)

    now = datetime.now(timezone.utc)
    pres = CasePresentation(
        session_id=session.id,
        case_id=case.id,
        order_index=body.orderIndex,
        started_at=now,
        ended_at=None,
        duration_ms=None,
    )
    db.add(pres)
    await db.commit()
    await db.refresh(pres)
    return CaseOpenOut(casePresentationId=pres.id)
