from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.db.models import Action, Case, CasePresentation, CaseSurvey, Session
from app.schemas.common import EscalateSubtype, SelectedAction
from app.services.edit_distance import levenshtein

router = APIRouter(prefix="/api/action", tags=["action"])


class TimingIn(BaseModel):
    startedAt: int  # epoch ms (client clock; server records own ts too)
    endedAt: int
    durationMs: int = Field(ge=0)


class QuickSurveyIn(BaseModel):
    item1: int = Field(ge=1, le=7)
    item2: int = Field(ge=1, le=7)
    item3: int = Field(ge=1, le=7)


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


class ActionIn(BaseModel):
    sessionId: str
    caseId: str
    orderIndex: int
    isPractice: bool = False
    selectedAction: SelectedAction
    finalReplyText: str
    escalateSubtype: EscalateSubtype | None = None
    quickSurvey: QuickSurveyIn
    timing: TimingIn
    clientStats: ClientStatsIn | None = None


class ActionResponse(BaseModel):
    ok: bool
    casePresentationId: str
    editDistance: int


def _to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


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

    edit_distance = levenshtein(case.ai_draft, body.finalReplyText)

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

    sa = body.selectedAction
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
            final_reply_text=body.finalReplyText,
            final_reply_char_count=len(body.finalReplyText),
            edit_distance=edit_distance,
            client_stats=(
                body.clientStats.model_dump() if body.clientStats else None
            ),
        )
    )
    db.add(
        CaseSurvey(
            case_presentation_id=presentation.id,
            safe_to_send=body.quickSurvey.item1,
            confidence_in_judgment=body.quickSurvey.item2,
            ai_draft_helpful=body.quickSurvey.item3,
        )
    )
    await db.commit()

    return ActionResponse(
        ok=True,
        casePresentationId=presentation.id,
        editDistance=edit_distance,
    )
