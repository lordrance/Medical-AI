from __future__ import annotations

import io
import json
import zipfile
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import db_session
from app.core.security import require_admin
from app.db.models import (
    Action,
    Case,
    CasePresentation,
    CaseSurvey,
    CohortSummary,
    LLMCall,
    OrderTemplate,
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
from app.services.database_dump import full_database_dump_bytes

router = APIRouter(prefix="/api/admin", tags=["admin"])

TableName = Literal[
    "participants",
    "sessions",
    "case_presentations",
    "actions",
    "case_surveys",
    "post_surveys",
    "ui_events",
    "cases",
    "order_templates",
    "llm_calls",
    "cohort_summaries",
    "summary",
]

EXPORT_DATA_TABLES: tuple[str, ...] = (
    "participants",
    "sessions",
    "case_presentations",
    "actions",
    "case_surveys",
    "post_surveys",
    "ui_events",
    "cases",
    "order_templates",
    "llm_calls",
    "cohort_summaries",
    "summary",
)


@router.get("/export/full-database")
async def export_full_database(request: Request) -> Response:
    """Download entire DB as SQL (SQLite: iterdump; Postgres: pg_dump). Admin only."""
    require_admin(request)
    try:
        content, filename, media_type = full_database_dump_bytes()
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/export/bundle")
async def export_bundle(
    request: Request,
    tables: str | None = Query(
        None,
        description="Comma-separated table names; omit for default study bundle.",
    ),
    db: AsyncSession = Depends(db_session),
) -> Response:
    """ZIP of CSV files for selected tables (admin only)."""
    require_admin(request)
    if tables:
        names = [t.strip() for t in tables.split(",") if t.strip()]
        invalid = [t for t in names if t not in EXPORT_DATA_TABLES]
        if invalid:
            raise HTTPException(
                400,
                f"unknown tables: {invalid}; allowed: {list(EXPORT_DATA_TABLES)}",
            )
        chosen = names
    else:
        chosen = list(EXPORT_DATA_TABLES)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in chosen:
            rows = await _load_table(name, db)
            if name == "summary":
                flat = flatten_summary(rows)  # type: ignore[arg-type]
                csv_text = to_csv(flat)
            else:
                csv_text = to_csv(rows)  # type: ignore[arg-type]
            zf.writestr(f"{name}.csv", csv_text.encode("utf-8"))
    buf.seek(0)
    payload = buf.getvalue()
    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="study_export.zip"',
        },
    )


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
        return JSONResponse(
            content=rows,
            headers={"Content-Disposition": f'attachment; filename="{table}.json"'},
        )

    if table == "summary":
        flat = flatten_summary(rows)  # type: ignore[arg-type]
        csv_text = to_csv(flat)
    else:
        csv_text = to_csv(rows)  # type: ignore[arg-type]

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
                "preSpecialty": r.specialty,
                "preTrainingLevel": r.training_level,
                "preYearsPostResidency": r.years_practice,
                "preWeeklyMsgVolume": r.weekly_message_volume,
                "preAiDraftingFamiliarity": r.ai_familiarity,
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
                    "actionReasonCode": r.action_reason_code,
                    "actionReasonText": r.action_reason_text,
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
                "caseDecisionConfidence": r.case_decision_confidence,
                "caseDraftHelpfulness": r.case_draft_helpfulness,
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

    if table == "cases":
        rows = (await db.execute(select(Case))).scalars().all()
        return [
            {
                "caseId": r.id,
                "isPractice": r.is_practice,
                "riskLevel": r.risk_level,
                "defectPresent": r.defect_present,
                "defectType": r.defect_type,
                "purpose": r.purpose,
                "patientMessage": r.patient_message,
                "chartSnapshotJson": json.dumps(r.chart_snapshot, ensure_ascii=False),
                "aiDraft": r.ai_draft,
                "factsUsedJson": json.dumps(r.facts_used, ensure_ascii=False),
                "riskCue": r.risk_cue,
                "checklistJson": json.dumps(r.checklist, ensure_ascii=False),
                "goldAction": r.gold_action,
                "goldActionAlternatesJson": json.dumps(
                    r.gold_action_alternates, ensure_ascii=False
                ),
                "version": r.version,
                "language": r.language,
            }
            for r in rows
        ]

    if table == "order_templates":
        rows = (await db.execute(select(OrderTemplate))).scalars().all()
        return [
            {
                "orderTemplateId": r.id,
                "orderJson": json.dumps(r.order, ensure_ascii=False),
            }
            for r in rows
        ]

    if table == "llm_calls":
        rows = (await db.execute(select(LLMCall))).scalars().all()
        return [
            {
                "llmCallId": r.id,
                "purpose": r.purpose,
                "provider": r.provider,
                "model": r.model,
                "promptText": r.prompt_text,
                "responseText": r.response_text,
                "promptTokens": r.prompt_tokens,
                "completionTokens": r.completion_tokens,
                "latencyMs": r.latency_ms,
                "error": r.error,
                "createdAt": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    if table == "cohort_summaries":
        rows = (await db.execute(select(CohortSummary))).scalars().all()
        return [
            {
                "cohortSummaryId": r.id,
                "payloadJson": json.dumps(r.payload, ensure_ascii=False),
                "summaryText": r.summary_text,
                "createdAt": r.created_at.isoformat() if r.created_at else None,
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
