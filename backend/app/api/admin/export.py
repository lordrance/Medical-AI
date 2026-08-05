"""★ 数据导出 —— 你写论文时取数据的地方。

三种导出方式，从粗到细：

  GET /api/admin/export/full-database  整库 SQL 备份（最完整，能原样还原）
  GET /api/admin/export/bundle         ZIP 打包多张表的 CSV（★ 最常用）
  GET /api/admin/export?table=xxx      单张表，CSV 或 JSON

★ 安全：三个接口都要管理员 token。后台前端用 downloadWithToken()
下载（fetch + Blob），保证 token 只走请求头、不进网址。
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
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
    """Download entire DB as SQL (SQLite: iterdump; Postgres: pg_dump). Admin only.

    中文：整库导出。生产环境走 pg_dump，生成的文件能原样还原一个数据库。
    这是最保险的备份方式（服务器上每天也会自动生成一份，见 docker-compose
    里的 backup 容器）。
    """
    require_admin(request)
    try:
        # pg_dump / iterdump is a blocking subprocess+IO. Run it in a thread so
        # it does not freeze this worker's event loop (which would make every
        # participant routed to this worker hang, and — past gunicorn's timeout
        # — get the worker SIGKILLed mid-request).
        #
        # ★ 中文（这是一个修过的真 bug）：pg_dump 是阻塞式的外部进程调用。
        # 直接在 async 函数里调，会把这个 worker 的事件循环整个卡住——
        # 期间所有被分到这个 worker 的医生都会卡死；超过 gunicorn 的
        # 120 秒超时后，worker 还会被强杀，他们的请求直接失败。
        # run_in_threadpool 把它挪到独立线程里跑，事件循环继续服务别人。
        content, filename, media_type = await run_in_threadpool(
            full_database_dump_bytes
        )
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
    """ZIP of CSV files for selected tables (admin only).

    ★ 中文：最常用的导出方式。一个 ZIP 里每张表一个 CSV，
    解压后直接用 Excel / SPSS / R 打开。不传 tables 参数就导全部。
    """
    require_admin(request)
    if tables:
        names = [t.strip() for t in tables.split(",") if t.strip()]
        # ★ 白名单校验：只允许导出 EXPORT_DATA_TABLES 里列出的表名。
        # 不校验的话，表名会被拼进 SQL，等于开了个注入口子。
        invalid = [t for t in names if t not in EXPORT_DATA_TABLES]
        if invalid:
            raise HTTPException(
                400,
                f"unknown tables: {invalid}; allowed: {list(EXPORT_DATA_TABLES)}",
            )
        chosen = names
    else:
        chosen = list(EXPORT_DATA_TABLES)

    # BytesIO = 内存里的假文件。ZIP 直接在内存里打包，不落磁盘，
    # 省得还要考虑临时文件清理。
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in chosen:
            rows = await _load_table(name, db)
            if name == "summary":
                # summary 是嵌套 JSON，要先摊平才能塞进 CSV
                flat = flatten_summary(rows)  # type: ignore[arg-type]
                csv_text = to_csv(flat)
            else:
                csv_text = to_csv(rows)  # type: ignore[arg-type]
            # ★ 必须用 utf-8 编码，否则中文答案在 CSV 里全是乱码
            zf.writestr(f"{name}.csv", csv_text.encode("utf-8"))
    buf.seek(0)  # 把「读写指针」拨回开头，否则读出来是空的
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
                "completion_code": f"AIDR-{r.id[-8:].upper()}" if r.completed_flag else None,
                "participant_id": r.id,
                "condition": r.condition,
                "order_template_id": r.order_template_id,
                "pre_specialty": r.pre_specialty,
                "pre_training_level": r.pre_training_level,
                "pre_years_post_residency": r.pre_years_post_residency,
                "pre_weekly_msg_volume": r.pre_weekly_msg_volume,
                "pre_ai_drafting_familiarity": r.pre_ai_drafting_familiarity,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "completed_flag": r.completed_flag,
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
                    "action_id": r.id,
                    "case_presentation_id": r.case_presentation_id,
                    "session_id": p.session_id if p else None,
                    "participant_id": sess.participant_id if sess else None,
                    "case_id": p.case_id if p else None,
                    "order_index": p.order_index if p else None,
                    "selected_action": r.selected_action,
                    "case_action_choice": r.case_action_choice,
                    "log_final_action": r.log_final_action,
                    "case_action_reason": (
                        json.dumps(r.case_action_reason, ensure_ascii=False)
                        if r.case_action_reason is not None
                        else None
                    ),
                    "send_as_is_flag": r.send_as_is_flag,
                    "edit_flag": r.edit_flag,
                    "discard_flag": r.discard_flag,
                    "escalate_flag": r.escalate_flag,
                    "escalate_subtype": r.escalate_subtype,
                    "escalate_reason": r.escalate_reason,
                    "final_reply_text": r.final_reply_text,
                    "final_reply_char_count": r.final_reply_char_count,
                    "edit_distance": r.edit_distance,
                    "gold_action": gold,
                    "gold_action_match": match,
                    "client_stats": (
                        json.dumps(r.client_stats, ensure_ascii=False)
                        if r.client_stats is not None
                        else None
                    ),
                    "server_received_at": (
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
                "case_survey_id": r.id,
                "case_presentation_id": r.case_presentation_id,
                "session_id": r.presentation.session_id if r.presentation else None,
                "participant_id": (
                    r.presentation.session.participant_id
                    if r.presentation and r.presentation.session
                    else None
                ),
                "case_id": r.presentation.case_id if r.presentation else None,
                "case_decision_confidence": r.case_decision_confidence,
                "case_draft_helpfulness": r.case_draft_helpfulness,
                "server_received_at": (
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
