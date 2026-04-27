from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.db.models import Case, Participant, Session
from app.schemas.case import CasePayload, CaseResponse, GuardrailContent

router = APIRouter(prefix="/api/case", tags=["case"])


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

    case = await db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")

    is_guardrail = participant.condition == "guardrail"
    return CaseResponse(
        case=CasePayload(
            id=case.id,
            isPractice=case.is_practice,
            riskLevel=case.risk_level,
            patientMessage=case.patient_message,
            chartSnapshot=case.chart_snapshot,
            aiDraft=case.ai_draft,
            guardrail=(
                GuardrailContent(
                    factsUsed=case.facts_used,
                    riskCue=case.risk_cue,
                    checklist=case.checklist,
                )
                if is_guardrail
                else None
            ),
        )
    )
