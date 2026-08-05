"""★ 全系统最核心的接口：医生提交一道题的作答。

医生在一道题上做完这一串动作后，前端把它们打包成一个请求发到这里：
  1. 看患者消息、展开病历、读 AI 草稿
  2. 选一个处理方式（原样发送 / 修改后发 / 重写 / 上报）
  3. （如果选了修改或重写）写下最终回复
  4. 选一个理由
  5. 答两道小量表（对判断有多大信心、AI 草稿有多大帮助）

这里会写三张表：
  case_presentations —— 更新这道题的起止时间和用时
  actions            —— 医生的选择、最终文本、编辑距离、行为指标
  case_surveys       —— 那两道小量表的分数

★ 幂等：同一道题重复提交，只保留**第一次**的答案，后面的请求原样返回
第一次的结果。这样医生网络卡了重复点提交也不会出错、不会产生重复数据。
"""

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

# 把四个处理方式映射成问卷 PDF 里规定的编号（1/2/3/4），
# 这样导出的数据能直接对上论文里的编码表。
_CHOICE_TO_PDF: dict[SelectedAction, int] = {
    SelectedAction.send_as_is: 1,        # 原样发送
    SelectedAction.edit_then_send: 2,    # 修改后发送
    SelectedAction.discard_and_rewrite: 3,  # 弃用并重写
    SelectedAction.escalate: 4,          # 上报/转诊
}


class TimingIn(BaseModel):
    """这道题花了多长时间。时间戳由浏览器提供，服务器另外也记自己的时间。"""

    startedAt: int  # epoch ms (client clock; server records own ts too)
    endedAt: int
    durationMs: int = Field(ge=0)  # ge=0 表示不接受负数


class QuickCaseSurveyIn(BaseModel):
    """案例内嵌入式量表（问卷 7.0）：判断信心、AI 起草帮助感。"""

    caseDecisionConfidence: int = Field(ge=1, le=5)
    caseDraftHelpfulness: int = Field(ge=1, le=5)


class ClientStatsIn(BaseModel):
    """前端上报的原始过程量；落库时仅抽取用于计算 PDF 第五节 log_* 的字段。

    中文：这些是「医生是怎么看这道题的」的行为数据，用来分析他们有没有
    认真核对，还是扫一眼就点了发送。全部由浏览器在答题过程中累计。
    """

    timeToFirstClickMs: int | None = None            # 从看到题到第一次点击隔了多久
    panelClickCounts: dict[str, int] = Field(default_factory=dict)  # 各面板点了几次
    editKeystrokes: int = 0                          # 在编辑框里敲了几次键
    editBoxOpenedCount: int = 0                      # 打开编辑框几次
    interactionMetrics: dict[str, object] | None = None  # 展开病历次数等细项
    draftScrollEventCount: int = 0                   # AI 草稿区滚动了几次
    draftScrollMaxDepthRatio: float = 0.0            # 最深滚到草稿的百分之几（0~1）
    draftSectionDwellMs: int = 0                     # 在草稿区停留了多久


class ActionIn(BaseModel):
    """前端提交上来的完整作答包。字段不合规会被 Pydantic 直接挡下，返回 422。"""

    sessionId: str
    caseId: str
    orderIndex: int                       # 第几题（-1 = 练习题）
    isPractice: bool = False
    selectedAction: SelectedAction        # 四选一：原样发/改后发/重写/上报
    finalReplyText: str                   # 医生最终定稿的回复文本
    escalateSubtype: EscalateSubtype | None = None  # 选「上报」时的子类型
    escalateReason: str | None = None     # 选「上报」时必填的理由
    caseActionReasonCode: ActionReasonCode  # 为什么这么选（枚举）
    caseActionReasonText: str | None = None # 选「其他」时必填的补充说明
    quickSurvey: QuickCaseSurveyIn        # 两道小量表
    timing: TimingIn                      # 用时
    clientStats: ClientStatsIn | None = None  # 行为数据（可缺，缺了填 0）

    @model_validator(mode="after")
    def _escalate_requires_reason(self) -> ActionIn:
        """选了「上报」就必须写理由，否则这条数据没有分析价值。"""
        if self.selectedAction == SelectedAction.escalate:
            if not (self.escalateReason or "").strip():
                raise ValueError("escalateReason is required when escalating")
        return self

    @model_validator(mode="after")
    def _other_reason_requires_text(self) -> ActionIn:
        """理由选了「其他」就必须写清楚是什么，否则等于没选。"""
        if self.caseActionReasonCode == ActionReasonCode.other:
            if not (self.caseActionReasonText or "").strip():
                raise ValueError("caseActionReasonText is required when reason is other")
        return self


class ActionResponse(BaseModel):
    ok: bool
    casePresentationId: str
    editDistance: int  # 医生把 AI 草稿改了多少（字符级差异）


def _to_dt(ms: int) -> datetime:
    """把浏览器传来的毫秒时间戳转成带时区的 datetime（统一用 UTC 存）。"""
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def build_pdf_autolog_client_stats(
    body: ActionIn, incoming: dict[str, Any] | None
) -> dict[str, Any]:
    """问卷 PDF 第五节「后台自动记录」：仅写入与 PDF 编码词一致的 log_* 键（不含派生/人工编码）。

    中文：把前端上报的原始行为数据，翻译成问卷 PDF 里定义好的那套变量名
    （全部以 log_ 开头）。这样你导出 CSV 后，列名能直接对上论文的编码表，
    不用再手工换算。键名不要随便改，改了就对不上研究工具了。
    """
    raw = incoming or {}
    t = body.timing
    out: dict[str, Any] = {
        # 这道题看了多少秒
        # 四个 log_xxx 是「独热编码」：选了哪个就那个为 1、其余为 0，方便统计
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
    """POST /api/action —— 提交一道题的作答。"""
    # 验明正身：会话和题目都必须真实存在。
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
    #
    # ★ 中文（这把锁解决的是一个真实发生过的线上事故）：
    # 医生点提交 → 手机网络卡住 → 前端等 25 秒超时、显示「提交失败」→
    # 医生再点一次。但第一个请求在服务器上**还在跑**（前端取消 fetch
    # 并不能取消后端的处理）。于是两个一模一样的请求同时写同一条记录。
    # actions 表对 case_presentation_id 有唯一约束，后写的那个直接违约崩掉，
    # 返回 500 —— 医生看到的就是「网络异常，请稍后重试」，
    # 而实际上他的答案早就存好了。
    # 加锁后两个请求排队执行，第二个会走下面的「已作答」分支原样返回。
    async with session_write_lock(db, session.id):
        return await _persist_action(db, session, case, body)


async def _persist_action(
    db: AsyncSession, session: Session, case: Case, body: ActionIn
) -> ActionResponse:
    """真正落库的部分。必须在 session_write_lock 里面调用。"""
    # ---- 第 1 步：这道题是不是已经答过了？----
    # selectinload 是「顺便把关联的 action 一起查出来」，避免后面每条再查一次。
    existing_stmt = (
        select(CasePresentation)
        .where(
            CasePresentation.session_id == session.id,
            CasePresentation.case_id == case.id,
        )
        .order_by(CasePresentation.started_at.asc())  # 排序保证多次调用结果一致
        .options(selectinload(CasePresentation.action))
    )
    existing_pres = (await db.execute(existing_stmt)).scalars().all()
    answered = next((p for p in existing_pres if p.action is not None), None)
    if answered is not None:
        # 已经答过 → 原样返回第一次的结果，不覆盖、不新增。
        # 这就是「幂等」：重复提交无害。也是「流程只能向前」的服务端保障。
        return ActionResponse(
            ok=True,
            casePresentationId=answered.id,
            editDistance=answered.action.edit_distance or 0,
        )

    # ---- 第 2 步：找那条「已打开、还没作答」的记录 ----
    # 正常情况下 /api/case/open 已经建好了，这里直接复用。
    in_progress_stmt = (
        select(CasePresentation)
        .outerjoin(Action, Action.case_presentation_id == CasePresentation.id)
        .where(
            CasePresentation.session_id == session.id,
            CasePresentation.case_id == case.id,
            Action.id.is_(None),  # ← 没挂 action = 还没作答
        )
        .order_by(CasePresentation.started_at.asc())
        .limit(1)
    )
    in_progress = (await db.execute(in_progress_stmt)).scalars().first()

    if in_progress is not None:
        # 找到了 → 补上起止时间和用时。
        presentation = in_progress
        presentation.order_index = body.orderIndex
        presentation.started_at = _to_dt(body.timing.startedAt)
        presentation.ended_at = _to_dt(body.timing.endedAt)
        presentation.duration_ms = body.timing.durationMs
        await db.flush()
    else:
        # 没找到 → 说明 /api/case/open 那次请求失败了（网络抖动）。
        # 不能因此拒绝作答，直接补建一条。
        presentation = CasePresentation(
            session_id=session.id,
            case_id=case.id,
            order_index=body.orderIndex,
            started_at=_to_dt(body.timing.startedAt),
            ended_at=_to_dt(body.timing.endedAt),
            duration_ms=body.timing.durationMs,
        )
        db.add(presentation)
        await db.flush()  # flush 让数据库生成 presentation.id，供下面外键引用

    # ---- 第 3 步：算编辑距离 ----
    # 把 AI 原始草稿和医生最终定稿做字符级比对，得出「改了多少」。
    # 0 = 一字未改；数值越大说明医生改动越多。这是核心研究指标之一。
    edit_distance = levenshtein(case.ai_draft, body.finalReplyText)

    sa = body.selectedAction
    # 把行为数据翻译成问卷 PDF 规定的 log_* 变量。
    incoming = body.clientStats.model_dump(exclude_none=True) if body.clientStats else None
    pdf_autolog = build_pdf_autolog_client_stats(body, incoming)

    # 理由存成 JSON：{"code": "safety_risk"}，选「其他」时再带上 text。
    reason_text = body.caseActionReasonText.strip() if body.caseActionReasonText else None
    reason_obj: dict[str, Any] = {"code": body.caseActionReasonCode.value}
    if reason_text:
        reason_obj["text"] = reason_text

    # ---- 第 4 步：写 actions 表（医生的选择本身）----
    db.add(
        Action(
            case_presentation_id=presentation.id,
            selected_action=sa.value,
            # 下面四个布尔字段是同一个信息的冗余存法。看着重复，但统计软件
            # （SPSS/R）做回归时直接吃这种 0/1 列最方便，省得再做哑变量。
            send_as_is_flag=sa == SelectedAction.send_as_is,
            edit_flag=sa == SelectedAction.edit_then_send,
            discard_flag=sa == SelectedAction.discard_and_rewrite,
            escalate_flag=sa == SelectedAction.escalate,
            escalate_subtype=(body.escalateSubtype.value if body.escalateSubtype else None),
            # 只有真的选了「上报」才存理由，否则存 None。
            # 防止医生先选上报写了理由、又改选别的，把废弃的理由留在库里。
            escalate_reason=(
                body.escalateReason.strip()
                if body.selectedAction == SelectedAction.escalate and body.escalateReason
                else None
            ),
            case_action_choice=_CHOICE_TO_PDF[sa],       # PDF 编码 1/2/3/4
            log_final_action=LOG_FINAL_ACTION_PDF[sa.value],  # PDF 规定的文字标签
            case_action_reason=reason_obj,
            final_reply_text=body.finalReplyText,        # 医生定稿的全文
            final_reply_char_count=len(body.finalReplyText),
            edit_distance=edit_distance,
            client_stats=pdf_autolog,
        )
    )
    # ---- 第 5 步：写 case_surveys 表（答完这题的两道小量表）----
    db.add(
        CaseSurvey(
            case_presentation_id=presentation.id,
            case_decision_confidence=body.quickSurvey.caseDecisionConfidence,  # 对判断的信心 1~5
            case_draft_helpfulness=body.quickSurvey.caseDraftHelpfulness,      # AI 草稿的帮助 1~5
        )
    )
    # 一次性提交。前面 flush 过的 presentation 改动和这两条新记录
    # 要么一起成功，要么一起失败，不会出现「有作答没量表」的半截数据。
    await db.commit()

    return ActionResponse(
        ok=True,
        casePresentationId=presentation.id,
        editDistance=edit_distance,
    )
