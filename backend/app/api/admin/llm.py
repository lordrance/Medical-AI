from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.core.security import require_admin
from app.db.models import (
    CohortSummary,
    LLMCall,
    Participant,
)
from app.llm.base import LLMUnavailable
from app.llm.factory import get_provider
from app.llm.prompts import load_prompt, render_template
from app.services.analysis import (
    completion_stats,
    confusion_matrix,
    per_case_stats,
    per_participant_stats,
)

router = APIRouter(prefix="/api/admin/llm", tags=["admin-llm"])


class CaseDraftIn(BaseModel):
    patientMessage: str
    chartSnapshot: dict[str, Any]


class ParticipantSummaryIn(BaseModel):
    participantId: str


class CaseDraftResponse(BaseModel):
    text: str
    provider: str
    model: str
    promptTokens: int | None = None
    completionTokens: int | None = None
    latencyMs: int


class SummaryResponse(BaseModel):
    summaryText: str
    provider: str
    model: str
    promptTokens: int | None = None
    completionTokens: int | None = None
    latencyMs: int


async def _record_llm_call(
    db: AsyncSession,
    *,
    purpose: str,
    provider: str,
    model: str,
    prompt_text: str,
    response_text: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    latency_ms: int,
    error: str | None = None,
) -> None:
    db.add(
        LLMCall(
            purpose=purpose,
            provider=provider,
            model=model,
            prompt_text=prompt_text,
            response_text=response_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            error=error,
        )
    )
    await db.commit()


@router.post("/case-draft", response_model=CaseDraftResponse)
async def llm_case_draft(
    request: Request,
    body: CaseDraftIn,
    db: AsyncSession = Depends(db_session),
) -> CaseDraftResponse:
    require_admin(request)
    provider = get_provider()
    system, user_tpl = load_prompt("case_draft")
    user = render_template(
        user_tpl,
        {
            "patientMessage": body.patientMessage,
            "chartSnapshotJson": json.dumps(
                body.chartSnapshot, ensure_ascii=False, indent=2
            ),
        },
    )
    try:
        resp = await provider.generate(system=system, user=user, max_tokens=512)
    except LLMUnavailable as e:
        await _record_llm_call(
            db,
            purpose="case_draft",
            provider=provider.name,
            model=provider.model,
            prompt_text=user[:4000],
            response_text="",
            prompt_tokens=None,
            completion_tokens=None,
            latency_ms=0,
            error=str(e),
        )
        raise HTTPException(503, str(e)) from e

    await _record_llm_call(
        db,
        purpose="case_draft",
        provider=resp.provider,
        model=resp.model,
        prompt_text=user[:4000],
        response_text=resp.text,
        prompt_tokens=resp.prompt_tokens,
        completion_tokens=resp.completion_tokens,
        latency_ms=resp.latency_ms,
    )
    return CaseDraftResponse(
        text=resp.text,
        provider=resp.provider,
        model=resp.model,
        promptTokens=resp.prompt_tokens,
        completionTokens=resp.completion_tokens,
        latencyMs=resp.latency_ms,
    )


@router.post("/participant-summary", response_model=SummaryResponse)
async def llm_participant_summary(
    request: Request,
    body: ParticipantSummaryIn,
    db: AsyncSession = Depends(db_session),
) -> SummaryResponse:
    require_admin(request)
    pt = await db.get(Participant, body.participantId)
    if pt is None:
        raise HTTPException(404, "Unknown participant")

    pp = await per_participant_stats(db)
    target = next((x for x in pp if x["participantId"] == body.participantId), None)
    if target is None:
        # No formal-case data yet for this participant. Provide skeleton context.
        target = {
            "participantId": body.participantId,
            "condition": pt.condition,
            "total": 0,
            "matchGold": 0,
            "accuracy": 0.0,
            "errorSurvivalCount": 0,
            "appropriateEscalationCount": 0,
            "meanDurationMs": 0,
            "meanEditDistance": 0,
        }
    target["specialty"] = pt.specialty
    target["trainingLevel"] = pt.training_level

    provider = get_provider()
    system, user_tpl = load_prompt("participant_summary")
    user = render_template(
        user_tpl,
        {"participantStatsJson": json.dumps(target, ensure_ascii=False, indent=2)},
    )
    try:
        resp = await provider.generate(system=system, user=user, max_tokens=600)
    except LLMUnavailable as e:
        raise HTTPException(503, str(e)) from e

    await _record_llm_call(
        db,
        purpose="participant_summary",
        provider=resp.provider,
        model=resp.model,
        prompt_text=user[:4000],
        response_text=resp.text,
        prompt_tokens=resp.prompt_tokens,
        completion_tokens=resp.completion_tokens,
        latency_ms=resp.latency_ms,
    )
    return SummaryResponse(
        summaryText=resp.text,
        provider=resp.provider,
        model=resp.model,
        promptTokens=resp.prompt_tokens,
        completionTokens=resp.completion_tokens,
        latencyMs=resp.latency_ms,
    )


@router.post("/cohort-summary", response_model=SummaryResponse)
async def llm_cohort_summary(
    request: Request, db: AsyncSession = Depends(db_session)
) -> SummaryResponse:
    require_admin(request)
    cohort = {
        "completion": await completion_stats(db),
        "confusionMatrix": await confusion_matrix(db),
        "perCase": await per_case_stats(db),
        "perParticipant": await per_participant_stats(db),
    }

    provider = get_provider()
    system, user_tpl = load_prompt("cohort_summary")
    user = render_template(
        user_tpl,
        {"cohortStatsJson": json.dumps(cohort, ensure_ascii=False, indent=2)},
    )
    try:
        resp = await provider.generate(system=system, user=user, max_tokens=900)
    except LLMUnavailable as e:
        raise HTTPException(503, str(e)) from e

    db.add(
        CohortSummary(
            payload=cohort,
            summary_text=resp.text,
        )
    )
    await _record_llm_call(
        db,
        purpose="cohort_summary",
        provider=resp.provider,
        model=resp.model,
        prompt_text=user[:4000],
        response_text=resp.text,
        prompt_tokens=resp.prompt_tokens,
        completion_tokens=resp.completion_tokens,
        latency_ms=resp.latency_ms,
    )
    return SummaryResponse(
        summaryText=resp.text,
        provider=resp.provider,
        model=resp.model,
        promptTokens=resp.prompt_tokens,
        completionTokens=resp.completion_tokens,
        latencyMs=resp.latency_ms,
    )


@router.get("/health")
async def llm_health(request: Request) -> dict:
    require_admin(request)
    provider = get_provider()
    ok = await provider.health()
    return {"provider": provider.name, "model": provider.model, "ok": ok}
