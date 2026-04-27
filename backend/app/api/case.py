from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.db.models import Case, Participant, Session
from app.llm.base import LLMUnavailable
from app.llm.factory import get_provider
from app.llm.prompts import load_prompt, render_template
from app.schemas.case import CasePayload, CaseResponse, GuardrailContent

router = APIRouter(prefix="/api/case", tags=["case"])


async def _generate_case_draft(case: Case) -> str:
    """Generate patient-facing draft from current case context via configured LLM."""
    provider = get_provider()
    system, user_tpl = load_prompt("case_draft")
    user = render_template(
        user_tpl,
        {
            "patientMessage": case.patient_message,
            "chartSnapshotJson": json.dumps(case.chart_snapshot, ensure_ascii=False, indent=2),
        },
    )
    try:
        resp = await provider.generate(system=system, user=user, max_tokens=512)
        return resp.text
    except LLMUnavailable:
        # Fallback to seeded draft when LLM is temporarily unavailable.
        return case.ai_draft


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
    ai_draft = await _generate_case_draft(case)

    return CaseResponse(
        case=CasePayload(
            id=case.id,
            isPractice=case.is_practice,
            riskLevel=case.risk_level,
            patientMessage=case.patient_message,
            chartSnapshot=case.chart_snapshot,
            aiDraft=ai_draft,
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
