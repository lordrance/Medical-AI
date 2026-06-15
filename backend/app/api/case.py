from __future__ import annotations

import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.db.models import Case, Participant, Session
from app.llm.base import LLMUnavailable
from app.llm.factory import get_provider
from app.llm.prompts import load_prompt, render_template
from app.schemas.case import CasePayload, CaseResponse, GuardrailContent

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/case", tags=["case"])


async def _generate_ai_risk_tip(case: Case) -> str:
    """LLM-generated AI risk tip; fallback to seeded risk_cue."""
    provider = get_provider()
    system, user_tpl = load_prompt("risk_tip")
    user = render_template(
        user_tpl,
        {
            "patientMessage": case.patient_message,
            "chartSnapshotJson": json.dumps(
                case.chart_snapshot, ensure_ascii=False, indent=2
            ),
            "factsUsedJson": json.dumps(case.facts_used, ensure_ascii=False),
        },
    )
    try:
        resp = await provider.generate(system=system, user=user, max_tokens=256)
        text = (resp.text or "").strip()
        if text:
            return text
    except LLMUnavailable:
        pass
    return case.risk_cue


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
        logger.warning("session_not_found", session_id=sessionId, case_id=case_id)
        raise HTTPException(404, "Unknown session")
    participant = await db.get(Participant, session.participant_id)
    if participant is None:
        logger.warning("participant_not_found", participant_id=session.participant_id, session_id=sessionId)
        raise HTTPException(404, "Unknown participant")

    case = await db.get(Case, case_id)
    if case is None:
        logger.warning("case_not_found", case_id=case_id, session_id=sessionId)
        raise HTTPException(404, "Case not found")

    is_guardrail = participant.condition == "guardrail"
    ai_draft = await _generate_case_draft(case)
    risk_for_guardrail = (
        await _generate_ai_risk_tip(case) if is_guardrail else case.risk_cue
    )

    logger.info(
        "case_loaded",
        session_id=sessionId,
        case_id=case_id,
        is_practice=case.is_practice,
        condition=participant.condition,
    )

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
                    riskCue=risk_for_guardrail,
                    checklist=[],
                )
                if is_guardrail
                else None
            ),
        )
    )
