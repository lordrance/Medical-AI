"""
================================================================================
文件作用：管理员专用的 AI 功能 —— 帮你写研究总结
================================================================================

★ 先说最重要的一件事：**这几个接口和医生完全无关。**

  V4 的医生端一次都不会调用 AI（题目里的 AI 草稿是预先写死在 cases.json 里
  的，原因见 api/case.py 开头的长注释）。这个文件里的接口只有你在管理后台
  主动点按钮时才会跑。

  所以生产环境的 llm_calls 表是 0 行，健康检查里 llmEnabled 也是 false
  （因为 LLM_PROVIDER=disabled）。要用这些功能，得先在服务器的 .env 里
  改成 deepseek 并配上 API key。

四个接口：
  POST /api/admin/llm/case-draft           给一段患者消息，让 AI 起草回复
                                           （出题时打草稿用，不是给医生的）
  POST /api/admin/llm/participant-summary  让 AI 总结某一位医生的表现
  POST /api/admin/llm/cohort-summary       ★ 让 AI 总结全体数据（写论文用）
  GET  /api/admin/llm/health               AI 服务通不通

--------------------------------------------------------------------------------
★ 一条铁律：每次调用 AI 都必须记账
--------------------------------------------------------------------------------
成功要调 record_llm_call，失败也要调（见 services/llm_audit.py）。
只在成功时记账是修过的一个真 bug（commit bc933f9）——出问题时最需要看的
恰恰是失败的那些调用。

--------------------------------------------------------------------------------
本文件的代码块（从上到下）：
--------------------------------------------------------------------------------
  第 1 块  router                     路由器
  第 2 块  四个 In/Response 类        请求和响应的格式
  第 3 块  llm_case_draft()           AI 起草回复（出题辅助）
  第 4 块  llm_participant_summary()  AI 总结单个医生
  第 5 块  llm_cohort_summary()       ★ AI 总结全体（写论文用）
  第 6 块  llm_health()               AI 服务健康检查
================================================================================
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.core.security import require_admin
from app.db.models import (
    CohortSummary,
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
from app.services.llm_audit import record_llm_call

# ── 第 1 块：路由器 ──────────────────────────────────────────────────────
router = APIRouter(prefix="/api/admin/llm", tags=["admin-llm"])


# ── 第 2 块：请求和响应的格式 ────────────────────────────────────────────
class CaseDraftIn(BaseModel):
    """给 AI 起草回复时要提供的输入：患者消息 + 病历。"""
    patientMessage: str
    chartSnapshot: dict[str, Any]


class ParticipantSummaryIn(BaseModel):
    """要总结哪位医生。"""

    participantId: str


class CaseDraftResponse(BaseModel):
    """AI 起草的结果，附带用量信息（算钱和排查用）。"""

    text: str
    provider: str
    model: str
    promptTokens: int | None = None
    completionTokens: int | None = None
    latencyMs: int


class SummaryResponse(BaseModel):
    """AI 总结的结果，字段含义同上。"""

    summaryText: str
    provider: str
    model: str
    promptTokens: int | None = None
    completionTokens: int | None = None
    latencyMs: int


# ── 第 3 块：AI 起草回复（出题辅助）─────────────────────────────────────
# ★ 这个接口生成的文本**不会**直接给医生看。它是你出题时打草稿用的：
#   生成一版，人工审核修改，再写进 cases.json 定稿。
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
        await record_llm_call(
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

    await record_llm_call(
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


# ── 第 4 块：AI 总结单个医生 ────────────────────────────────────────────
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
    target["pre_specialty"] = pt.pre_specialty
    target["pre_training_level"] = pt.pre_training_level

    provider = get_provider()
    system, user_tpl = load_prompt("participant_summary")
    user = render_template(
        user_tpl,
        {"participantStatsJson": json.dumps(target, ensure_ascii=False, indent=2)},
    )
    try:
        resp = await provider.generate(system=system, user=user, max_tokens=600)
    except LLMUnavailable as e:
        await record_llm_call(
            db,
            purpose="participant_summary",
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

    await record_llm_call(
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


# ── 第 5 块：AI 总结全体数据 ★ 写论文用 ─────────────────────────────────
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
        await record_llm_call(
            db,
            purpose="cohort_summary",
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

    db.add(
        CohortSummary(
            payload=cohort,
            summary_text=resp.text,
        )
    )
    await record_llm_call(
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


# ── 第 6 块：AI 服务健康检查 ────────────────────────────────────────────
@router.get("/health")
async def llm_health(request: Request) -> dict:
    require_admin(request)
    provider = get_provider()
    ok = await provider.health()
    return {"provider": provider.name, "model": provider.model, "ok": ok}
