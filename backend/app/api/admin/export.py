from __future__ import annotations

import json
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import db_session
from app.core.security import require_admin
from app.db.models import (
    Action,
    CasePresentation,
    CaseSurvey,
    Participant,
    PostSurvey,
    Session as SessionModel,
    UiEvent,
)
from app.services.analysis import (
    completion_stats,
    confusion_matrix,
    per_case_stats,
    per_participant_stats,
)
from app.services.csv_export import flatten_summary, to_csv

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

TableName = Literal[
    "participants",
    "sessions",
    "case_presentations",
    "actions",
    "case_surveys",
    "post_surveys",
    "ui_events",
    "summary",
]


@router.get("/export")
async def export(
    request: Request,
    table: TableName = Query("summary"),
    format: Literal["csv", "json"] = Query("csv"),
    db: AsyncSession = Depends(db_session),
) -> Response:
    require_admin(request)
    rows: Any = await _load_table(table, db)

    if format == "json":
        logger.info("export_completed", table=table, format=format)
        return JSONResponse(
            content=rows,
            headers={"Content-Disposition": f'attachment; filename="{table}.json"'},
        )

    if table == "summary":
        flat = flatten_summary(rows)  # type: ignore[arg-type]
        csv_text = to_csv(flat)
    else:
        csv_text = to_csv(rows)  # type: ignore[arg-type]

    logger.info("export_completed", table=table, format=format, row_count=len(rows))

    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{table}.csv"'},
    )


async def _load_table(table: str, db: AsyncSession) -> Any:
    if table == "participants":
        rows = (await db.execute(select(Participant))).scalars().all()
        return [
            {
                "participantId": r.id,
                "condition": r.condition,
                "orderTemplateId": r.order_template_id,
                "specialty": r.specialty,
                "trainingLevel": r.training_level,
                "yearsPractice": r.years_practice,
                "weeklyMessageVolume": r.weekly_message_volume,
                "priorAiUse": r.prior_ai_use,
                "aiFamiliarity": r.ai_familiarity,
                "aiBrandsUsed": r.ai_brands_used,
                "startedAt": r.started_at.isoformat() if r.started_at else None,
                "completedAt": r.completed_at.isoformat() if r.completed_at else None,
                "completedFlag": r.completed_flag,
            }
            for r in rows
        ]

    if table == "sessions":
        rows = (await db.execute(select(SessionModel))).scalars().all()
        return [
            {
                "sessionId": r.id,
                "participantId": r.participant_id,
                "status": r.status,
                "startedAt": r.started_at.isoformat() if r.started_at else None,
                "endedAt": r.ended_at.isoformat() if r.ended_at else None,
            }
            for r in rows
        ]

    if table == "case_presentations":
        stmt = select(CasePresentation).options(
            selectinload(CasePresentation.case),
            selectinload(CasePresentation.session),
        )
        rows = (await db.execute(stmt)).scalars().all()
        return [
            {
                "casePresentationId": r.id,
                "sessionId": r.session_id,
                "participantId": r.session.participant_id if r.session else None,
                "caseId": r.case_id,
                "isPractice": r.case.is_practice if r.case else None,
                "riskLevel": r.case.risk_level if r.case else None,
                "defectPresent": r.case.defect_present if r.case else None,
                "defectType": r.case.defect_type if r.case else None,
                "orderIndex": r.order_index,
                "startedAt": r.started_at.isoformat() if r.started_at else None,
                "endedAt": r.ended_at.isoformat() if r.ended_at else None,
                "durationMs": r.duration_ms,
            }
            for r in rows
        ]

    if table == "actions":
        stmt = select(Action).options(
            selectinload(Action.presentation)
            .selectinload(CasePresentation.case),
            selectinload(Action.presentation)
            .selectinload(CasePresentation.session),
        )
        rows = (await db.execute(stmt)).scalars().all()
        out = []
        for r in rows:
            p = r.presentation
            c = p.case if p else None
            sess = p.session if p else None
            alts = c.gold_action_alternates if c else []
            gold = c.gold_action if c else None
            match = (gold == r.selected_action) or (
                r.selected_action in (alts or [])
            )
            out.append(
                {
                    "actionId": r.id,
                    "casePresentationId": r.case_presentation_id,
                    "sessionId": p.session_id if p else None,
                    "participantId": sess.participant_id if sess else None,
                    "caseId": p.case_id if p else None,
                    "orderIndex": p.order_index if p else None,
                    "selectedAction": r.selected_action,
                    "sendAsIsFlag": r.send_as_is_flag,
                    "editFlag": r.edit_flag,
                    "discardFlag": r.discard_flag,
                    "escalateFlag": r.escalate_flag,
                    "escalateSubtype": r.escalate_subtype,
                    "escalateReason": r.escalate_reason,
                    "finalReplyText": r.final_reply_text,
                    "finalReplyCharCount": r.final_reply_char_count,
                    "editDistance": r.edit_distance,
                    "goldAction": gold,
                    "goldActionMatch": match,
                    "clientStatsJson": (
                        json.dumps(r.client_stats, ensure_ascii=False)
                        if r.client_stats is not None
                        else None
                    ),
                    "serverReceivedAt": (
                        r.server_received_at.isoformat() if r.server_received_at else None
                    ),
                }
            )
        return out

    if table == "case_surveys":
        stmt = select(CaseSurvey).options(
            selectinload(CaseSurvey.presentation).selectinload(
                CasePresentation.session
            )
        )
        rows = (await db.execute(stmt)).scalars().all()
        return [
            {
                "caseSurveyId": r.id,
                "casePresentationId": r.case_presentation_id,
                "sessionId": r.presentation.session_id if r.presentation else None,
                "participantId": (
                    r.presentation.session.participant_id
                    if r.presentation and r.presentation.session
                    else None
                ),
                "caseId": r.presentation.case_id if r.presentation else None,
                "safeToSend": r.safe_to_send,
                "confidenceInJudgment": r.confidence_in_judgment,
                "aiDraftHelpful": r.ai_draft_helpful,
                "serverReceivedAt": (
                    r.server_received_at.isoformat() if r.server_received_at else None
                ),
            }
            for r in rows
        ]

    if table == "post_surveys":
        rows = (await db.execute(select(PostSurvey))).scalars().all()
        return [
            {
                "postSurveyId": r.id,
                "sessionId": r.session_id,
                "participantId": r.participant_id,
                "payloadJson": json.dumps(r.payload, ensure_ascii=False),
                "serverReceivedAt": (
                    r.server_received_at.isoformat() if r.server_received_at else None
                ),
            }
            for r in rows
        ]

    if table == "ui_events":
        rows = (await db.execute(select(UiEvent))).scalars().all()
        return [
            {
                "uiEventId": r.id,
                "sessionId": r.session_id,
                "casePresentationId": r.case_presentation_id,
                "eventType": r.event_type,
                "payloadJson": (
                    json.dumps(r.payload, ensure_ascii=False)
                    if r.payload is not None
                    else None
                ),
                "clientTs": r.client_ts.isoformat() if r.client_ts else None,
                "serverTs": r.server_ts.isoformat() if r.server_ts else None,
            }
            for r in rows
        ]

    if table == "summary":
        completion = await completion_stats(db)
        cm = await confusion_matrix(db)
        pc = await per_case_stats(db)
        pp = await per_participant_stats(db)
        return {
            "completion": completion,
            "confusionMatrix": cm,
            "perCase": pc,
            "perParticipant": pp,
        }

    raise HTTPException(400, f"unknown table: {table}")
