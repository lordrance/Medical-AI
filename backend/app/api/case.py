from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.db.models import Action, Case, CasePresentation, Participant, Session
from app.llm.base import LLMUnavailable
from app.llm.factory import get_provider
from app.llm.prompts import load_prompt, render_template
from app.schemas.case import CasePayload, CaseResponse, GuardrailContent

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
    """Return the patient-facing AI draft.

    For *defect* cases (defect_present=True), the seed `ai_draft` is the intentional
    flawed text for the study. We must not call the LLM in that case, or the model
    will "fix" the error and break the experiment.
    """
    if case.defect_present:
        return case.ai_draft
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
    risk_for_guardrail = (
        await _generate_ai_risk_tip(case) if is_guardrail else case.risk_cue
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

    from datetime import datetime, timezone

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
