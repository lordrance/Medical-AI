from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import db_session
from app.db.models import Action, Case, CasePresentation, CaseSurvey, Session
from app.schemas.action_reason import ActionReasonCode
from app.schemas.common import EscalateSubtype, SelectedAction
from app.services.edit_distance import levenshtein

router = APIRouter(prefix="/api/action", tags=["action"])

_CHOICE_TO_PDF: dict[SelectedAction, int] = {
    SelectedAction.send_as_is: 1,
    SelectedAction.edit_then_send: 2,
    SelectedAction.discard_and_rewrite: 3,
    SelectedAction.escalate: 4,
}


class TimingIn(BaseModel):
    startedAt: int  # epoch ms (client clock; server records own ts too)
    endedAt: int
    durationMs: int = Field(ge=0)


class QuickCaseSurveyIn(BaseModel):
    """案例内嵌入式量表（问卷 7.0）：判断信心、AI 起草帮助感。"""

    caseDecisionConfidence: int = Field(ge=1, le=5)
    caseDraftHelpfulness: int = Field(ge=1, le=5)


class ClientStatsIn(BaseModel):
    timeToFirstClickMs: int | None = None
    panelClickCounts: dict[str, int] = Field(default_factory=dict)
    checklistChecked: list[bool] = Field(default_factory=list)
    checklistToggleCount: int = 0
    editKeystrokes: int = 0
    editBoxOpenedCount: int = 0
    pageBlurCount: int = 0
    pageFocusCount: int = 0
    visibilityHiddenMs: int = 0
    interactionMetrics: dict[str, object] | None = None
    draftScrollEventCount: int = 0
    draftScrollMaxDepthRatio: float = 0.0
    draftSectionDwellMs: int = 0


class ActionIn(BaseModel):
    sessionId: str
    caseId: str
    orderIndex: int
    isPractice: bool = False
    selectedAction: SelectedAction
    finalReplyText: str
    escalateSubtype: EscalateSubtype | None = None
    escalateReason: str | None = None
    caseActionReasonCode: ActionReasonCode
    caseActionReasonText: str | None = None
    quickSurvey: QuickCaseSurveyIn
    timing: TimingIn
    clientStats: ClientStatsIn | None = None

    @model_validator(mode="after")
    def _escalate_requires_reason(self) -> ActionIn:
        if self.selectedAction == SelectedAction.escalate:
            if not (self.escalateReason or "").strip():
                raise ValueError("escalateReason is required when escalating")
        return self

    @model_validator(mode="after")
    def _other_reason_requires_text(self) -> ActionIn:
        if self.caseActionReasonCode == ActionReasonCode.other:
            if not (self.caseActionReasonText or "").strip():
                raise ValueError("caseActionReasonText is required when reason is other")
        return self


class ActionResponse(BaseModel):
    ok: bool
    casePresentationId: str
    editDistance: int


def _to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _merge_log_fields(body: ActionIn, stats: dict[str, Any]) -> dict[str, Any]:
    """在 client_stats 中附加与问卷 7.0 第五节对应的 log_* / case_action_choice。"""
    t = body.timing
    stats["log_case_review_time_sec"] = round(t.durationMs / 1000.0, 3)
    if stats.get("timeToFirstClickMs") is not None:
        stats["log_time_to_first_action_sec"] = round(
            float(stats["timeToFirstClickMs"]) / 1000.0,
            3,
        )
    choice = _CHOICE_TO_PDF[body.selectedAction]
    stats["case_action_choice"] = choice
    stats["log_final_action"] = body.selectedAction.value
    stats["log_send_as_is"] = 1 if body.selectedAction == SelectedAction.send_as_is else 0
    stats["log_edit_then_send"] = (
        1 if body.selectedAction == SelectedAction.edit_then_send else 0
    )
    stats["log_discard_rewrite"] = (
        1 if body.selectedAction == SelectedAction.discard_and_rewrite else 0
    )
    stats["log_escalate"] = 1 if body.selectedAction == SelectedAction.escalate else 0
    stats["case_action_reason_code"] = body.caseActionReasonCode.value
    if body.caseActionReasonText:
        stats["case_action_reason_text"] = body.caseActionReasonText.strip()

    cs = body.clientStats
    if cs is not None:
        stats["log_edit_actions"] = cs.editKeystrokes + cs.editBoxOpenedCount
        im = cs.interactionMetrics or {}
        chart_ok = bool(im.get("chartEverExpandedToView"))
        guard_ok = bool(im.get("guardrailEverExpandedToView"))
        stats["log_source_panel_open"] = int(chart_ok or guard_ok)
        stats["log_help_risk_panel"] = int(guard_ok)
        stats["log_toggle_draft_source"] = int(im.get("draftSourceSwitchCount") or 0)
        clicks = cs.panelClickCounts or {}
        stats["log_verification_clicks"] = int(
            clicks.get("chart_panel", 0)
            + clicks.get("guardrail_panel", 0)
            + clicks.get("facts_panel", 0)
        )
        stats["log_scroll_dwell_draft"] = {
            "scrollEventCount": cs.draftScrollEventCount,
            "maxDepthRatio": cs.draftScrollMaxDepthRatio,
            "sectionDwellMs": cs.draftSectionDwellMs,
        }
    return stats


@router.post("", response_model=ActionResponse)
async def submit_action(
    body: ActionIn, db: AsyncSession = Depends(db_session)
) -> ActionResponse:
    session = await db.get(Session, body.sessionId)
    if session is None:
        raise HTTPException(404, "Unknown session")
    case = await db.get(Case, body.caseId)
    if case is None:
        raise HTTPException(404, "Unknown case")

    # Idempotent: same session + case already submitted (e.g. user pressed browser back
    # and submitted again) — return existing row, do not duplicate records.
    existing_stmt = (
        select(CasePresentation)
        .where(
            CasePresentation.session_id == session.id,
            CasePresentation.case_id == case.id,
        )
        .options(selectinload(CasePresentation.action))
    )
    existing_pres = (await db.execute(existing_stmt)).scalars().first()
    if existing_pres is not None and existing_pres.action is not None:
        return ActionResponse(
            ok=True,
            casePresentationId=existing_pres.id,
            editDistance=existing_pres.action.edit_distance or 0,
        )

    in_progress_stmt = (
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
    in_progress = (await db.execute(in_progress_stmt)).scalars().first()

    if in_progress is not None:
        presentation = in_progress
        presentation.order_index = body.orderIndex
        presentation.started_at = _to_dt(body.timing.startedAt)
        presentation.ended_at = _to_dt(body.timing.endedAt)
        presentation.duration_ms = body.timing.durationMs
        await db.flush()
    else:
        presentation = CasePresentation(
            session_id=session.id,
            case_id=case.id,
            order_index=body.orderIndex,
            started_at=_to_dt(body.timing.startedAt),
            ended_at=_to_dt(body.timing.endedAt),
            duration_ms=body.timing.durationMs,
        )
        db.add(presentation)
        await db.flush()

    edit_distance = levenshtein(case.ai_draft, body.finalReplyText)

    sa = body.selectedAction
    raw_stats: dict[str, Any] = (
        body.clientStats.model_dump(exclude_none=True) if body.clientStats else {}
    )
    merged_stats = _merge_log_fields(body, raw_stats)

    reason_text = (
        body.caseActionReasonText.strip()
        if body.caseActionReasonText
        else None
    )
    db.add(
        Action(
            case_presentation_id=presentation.id,
            selected_action=sa.value,
            send_as_is_flag=sa == SelectedAction.send_as_is,
            edit_flag=sa == SelectedAction.edit_then_send,
            discard_flag=sa == SelectedAction.discard_and_rewrite,
            escalate_flag=sa == SelectedAction.escalate,
            escalate_subtype=(
                body.escalateSubtype.value if body.escalateSubtype else None
            ),
            escalate_reason=(
                body.escalateReason.strip()
                if body.selectedAction == SelectedAction.escalate
                and body.escalateReason
                else None
            ),
            action_reason_code=body.caseActionReasonCode.value,
            action_reason_text=reason_text,
            final_reply_text=body.finalReplyText,
            final_reply_char_count=len(body.finalReplyText),
            edit_distance=edit_distance,
            client_stats=merged_stats,
        )
    )
    db.add(
        CaseSurvey(
            case_presentation_id=presentation.id,
            case_decision_confidence=body.quickSurvey.caseDecisionConfidence,
            case_draft_helpfulness=body.quickSurvey.caseDraftHelpfulness,
        )
    )
    await db.commit()

    return ActionResponse(
        ok=True,
        casePresentationId=presentation.id,
        editDistance=edit_distance,
    )
