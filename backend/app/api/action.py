from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import db_session
from app.db.locks import session_write_lock
from app.db.models import Action, Case, CasePresentation, CaseSurvey, Session
from app.schemas.action_reason import ActionReasonCode
from app.schemas.common import EscalateSubtype, LOG_FINAL_ACTION_PDF, SelectedAction
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
    """前端上报的原始过程量；落库时仅抽取用于计算 PDF 第五节 log_* 的字段。"""

    timeToFirstClickMs: int | None = None
    panelClickCounts: dict[str, int] = Field(default_factory=dict)
    editKeystrokes: int = 0
    editBoxOpenedCount: int = 0
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


def build_pdf_autolog_client_stats(
    body: ActionIn, incoming: dict[str, Any] | None
) -> dict[str, Any]:
    """问卷 PDF 第五节「后台自动记录」：仅写入与 PDF 编码词一致的 log_* 键（不含派生/人工编码）。"""
    raw = incoming or {}
    t = body.timing
    out: dict[str, Any] = {
        "log_case_review_time": round(t.durationMs / 1000.0, 3),
        "log_send_as_is": 1 if body.selectedAction == SelectedAction.send_as_is else 0,
        "log_edit_then_send": (1 if body.selectedAction == SelectedAction.edit_then_send else 0),
        "log_discard_rewrite": (
            1 if body.selectedAction == SelectedAction.discard_and_rewrite else 0
        ),
        "log_escalate": 1 if body.selectedAction == SelectedAction.escalate else 0,
    }
    ttfc = raw.get("timeToFirstClickMs")
    out["log_time_to_first_action"] = round(float(ttfc) / 1000.0, 3) if ttfc is not None else None

    cs = body.clientStats
    if cs is not None:
        out["log_edit_actions"] = cs.editKeystrokes + cs.editBoxOpenedCount
        im = cs.interactionMetrics or {}
        chart_ok = bool(im.get("chartEverExpandedToView"))
        guard_ok = bool(im.get("guardrailEverExpandedToView"))
        out["log_source_panel_open"] = int(chart_ok or guard_ok)
        out["log_help_risk_panel"] = int(guard_ok)
        out["log_toggle_draft_source"] = int(im.get("draftSourceSwitchCount") or 0)
        clicks = cs.panelClickCounts or {}
        out["log_verification_clicks"] = int(
            clicks.get("chart_panel", 0)
            + clicks.get("guardrail_panel", 0)
            + clicks.get("facts_panel", 0)
            + clicks.get("risk_panel", 0)
        )
        out["log_scroll_dwell_draft"] = {
            "section_dwell_sec": round(cs.draftSectionDwellMs / 1000.0, 4),
            "max_depth_ratio": float(cs.draftScrollMaxDepthRatio),
            "scroll_event_count": int(cs.draftScrollEventCount),
        }
    else:
        out["log_edit_actions"] = 0
        out["log_source_panel_open"] = 0
        out["log_help_risk_panel"] = 0
        out["log_toggle_draft_source"] = 0
        out["log_verification_clicks"] = 0
        out["log_scroll_dwell_draft"] = {
            "section_dwell_sec": 0.0,
            "max_depth_ratio": 0.0,
            "scroll_event_count": 0,
        }
    return out


@router.post("", response_model=ActionResponse)
async def submit_action(body: ActionIn, db: AsyncSession = Depends(db_session)) -> ActionResponse:
    session = await db.get(Session, body.sessionId)
    if session is None:
        raise HTTPException(404, "Unknown session")
    case = await db.get(Case, body.caseId)
    if case is None:
        raise HTTPException(404, "Unknown case")

    # A stalled submit that the participant retries leaves two identical
    # requests in flight. Serialize them so the "already answered?" check
    # below is authoritative; otherwise both pass it and the second insert
    # violates the UNIQUE on actions.case_presentation_id → 500.
    async with session_write_lock(db, session.id):
        return await _persist_action(db, session, case, body)


async def _persist_action(
    db: AsyncSession, session: Session, case: Case, body: ActionIn
) -> ActionResponse:
    existing_stmt = (
        select(CasePresentation)
        .where(
            CasePresentation.session_id == session.id,
            CasePresentation.case_id == case.id,
        )
        .order_by(CasePresentation.started_at.asc())
        .options(selectinload(CasePresentation.action))
    )
    existing_pres = (await db.execute(existing_stmt)).scalars().all()
    answered = next((p for p in existing_pres if p.action is not None), None)
    if answered is not None:
        return ActionResponse(
            ok=True,
            casePresentationId=answered.id,
            editDistance=answered.action.edit_distance or 0,
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
    incoming = body.clientStats.model_dump(exclude_none=True) if body.clientStats else None
    pdf_autolog = build_pdf_autolog_client_stats(body, incoming)

    reason_text = body.caseActionReasonText.strip() if body.caseActionReasonText else None
    reason_obj: dict[str, Any] = {"code": body.caseActionReasonCode.value}
    if reason_text:
        reason_obj["text"] = reason_text

    db.add(
        Action(
            case_presentation_id=presentation.id,
            selected_action=sa.value,
            send_as_is_flag=sa == SelectedAction.send_as_is,
            edit_flag=sa == SelectedAction.edit_then_send,
            discard_flag=sa == SelectedAction.discard_and_rewrite,
            escalate_flag=sa == SelectedAction.escalate,
            escalate_subtype=(body.escalateSubtype.value if body.escalateSubtype else None),
            escalate_reason=(
                body.escalateReason.strip()
                if body.selectedAction == SelectedAction.escalate and body.escalateReason
                else None
            ),
            case_action_choice=_CHOICE_TO_PDF[sa],
            log_final_action=LOG_FINAL_ACTION_PDF[sa.value],
            case_action_reason=reason_obj,
            final_reply_text=body.finalReplyText,
            final_reply_char_count=len(body.finalReplyText),
            edit_distance=edit_distance,
            client_stats=pdf_autolog,
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
