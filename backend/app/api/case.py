"""发题接口：把一道题的内容给前端，并记录「这个人开始看这道题了」。

两个接口：
  GET  /api/case/{case_id}  取题目内容（患者消息 + 病历 + AI 草稿）
  POST /api/case/open       建一条「某人开始看某题」的记录，供埋点关联用
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.db.locks import session_write_lock
from app.db.models import Action, Case, CasePresentation, Participant, Session
from app.schemas.case import CasePayload, CaseResponse

router = APIRouter(prefix="/api/case", tags=["case"])


# V4 design constraint: the AI draft shown to every participant for a given
# case must be byte-identical, otherwise the AI text becomes an uncontrolled
# experimental variable. So we never invoke the LLM during participant case
# rendering — we return the seeded `ai_draft` verbatim. The V3 live-LLM
# implementation (provider invocation, prompt rendering, llm_calls audit
# rows for case_draft / risk_tip) lives in git history at the V3 tag if a
# future revision needs to restore it.
#
# The guardrail UI is also intentionally not rendered (single-condition
# study), so factsUsed / riskCue / checklist seed data is exported as
# research metadata but not surfaced to participants.
#
# ★ 中文（这是整个研究最重要的一条规矩）：
# 同一道题，每个医生看到的 AI 草稿必须一模一样。所以医生端**绝对不会**
# 实时调用 AI 生成文本——那样每个人看到的内容就不同了，AI 文本会变成一个
# 不受控的实验变量，研究结论就不成立。这里只是把 cases.json 里预先写死的
# ai_draft 原样返回。（backend/tests/test_llm.py 有专门的测试守着这条规矩。）
#
# 另外：V3 有个「风险提示面板」（guardrail），V4 改成单一条件后不再显示，
# 但数据仍然导出，作为研究元数据保留。


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: str,
    sessionId: str = Query(...),
    db: AsyncSession = Depends(db_session),
) -> CaseResponse:
    """GET /api/case/{id} —— 取一道题的内容。

    这是整个系统调用最频繁的接口：每人 9 次（1 练习 + 8 正式）。
    """
    # 先验明正身：sessionId 是不是真的。伪造的 ID 直接 404，
    # 前端收到这个 404 会自动清掉本地会话、把人送回知情同意页重新开始。
    session = await db.get(Session, sessionId)
    if session is None:
        raise HTTPException(404, "Unknown session")
    participant = await db.get(Participant, session.participant_id)
    if participant is None:
        raise HTTPException(404, "Unknown participant")

    # Cases are read-only seed data — serve from memory when cached.
    #
    # 中文：题目内容是只读的固定数据，第一次查完就放进内存。
    # 100 个人同时答题时，这一步省掉了 900 次数据库查询。
    from app.core.cache import get as cache_get, set as cache_set

    cache_key = f"case:{case_id}"
    cached = cache_get(cache_key)
    if cached is not None:
        return CaseResponse(case=cached)

    case = await db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")

    # 只挑医生需要看到的字段返回。gold_action（标准答案）、defect_type
    # （这题埋的是什么错）等字段**不能**发给前端，否则被试能从网络请求里看到答案。
    payload = CasePayload(
        id=case.id,
        isPractice=case.is_practice,
        riskLevel=case.risk_level,
        patientMessage=case.patient_message,   # 患者发来的消息
        chartSnapshot=case.chart_snapshot,     # 病历摘要
        aiDraft=case.ai_draft,                 # AI 起草的回复（写死的，见文件头）
        guardrail=None,                        # V4 不显示风险提示面板
    )
    cache_set(cache_key, payload)
    return CaseResponse(case=payload)


class CaseOpenIn(BaseModel):
    sessionId: str
    caseId: str
    # orderIndex：这是第几道题。0~7 是正式题，-1 表示练习题。
    orderIndex: int = Field(..., ge=-1)


class CaseOpenOut(BaseModel):
    casePresentationId: str


@router.post("/open", response_model=CaseOpenOut)
async def open_case(
    body: CaseOpenIn,
    db: AsyncSession = Depends(db_session),
) -> CaseOpenOut:
    """Create or return an in-progress CasePresentation for UI event correlation.

    中文：建一条「某人开始看某题」的记录，返回它的 ID。
    前端拿到这个 ID 后，后续所有埋点都会带上它，这样才知道
    「展开了病历」这个动作是发生在哪道题上的。

    ★ 这个接口失败不影响答题。前端把它当成纯埋点，即使 500 了照样渲染题目、
    照样能提交答案（见 frontend/src/app/case/[order]/page.tsx 的 Step 2）。
    """
    session = await db.get(Session, body.sessionId)
    if session is None:
        raise HTTPException(404, "Unknown session")
    case = await db.get(Case, body.caseId)
    if case is None:
        raise HTTPException(404, "Case not found")

    # Two opens for the same case can overlap (a retried request, a fast
    # back-forward). Without serialization both miss the reuse lookup below
    # and each inserts its own row — production had accumulated 23 such
    # duplicate presentations before this guard.
    #
    # 中文：同一道题的两次「打开」有可能同时发生（网络重试、快速前后翻页）。
    # 下面 _open_presentation 是「先查有没有 → 没有就新建」的写法，
    # 两个请求同时跑就会都查不到、都新建 → 产生重复行。
    # 生产库在加这把锁之前已经积累了 23 组这样的重复数据。
    # 锁是按 sessionId 加的，只挡同一个人自己的请求，不同人之间互不影响。
    async with session_write_lock(db, session.id):
        return await _open_presentation(db, session, case, body.orderIndex)


async def _open_presentation(
    db: AsyncSession, session: Session, case: Case, order_index: int
) -> CaseOpenOut:
    """真正干活的部分。必须在 session_write_lock 里面调用。"""
    # 先找找有没有「已经打开、但还没提交答案」的记录可以复用。
    # 判断标准：这条 case_presentation 上没有挂 action（outerjoin 后 Action.id 为空）。
    # 有的话说明是同一个人刷新了页面 / 重新打开，复用即可，不要新建。
    reuse_stmt = (
        select(CasePresentation)
        .outerjoin(Action, Action.case_presentation_id == CasePresentation.id)
        .where(
            CasePresentation.session_id == session.id,
            CasePresentation.case_id == case.id,
            Action.id.is_(None),  # ← 没有作答记录 = 还在进行中
        )
        .order_by(CasePresentation.started_at.asc())  # 有多条时取最早那条，保证结果稳定
        .limit(1)
    )
    existing = (await db.execute(reuse_stmt)).scalars().first()
    if existing is not None:
        existing.order_index = order_index
        await db.commit()
        return CaseOpenOut(casePresentationId=existing.id)

    # 没有可复用的，才新建一条。
    now = datetime.now(timezone.utc)
    pres = CasePresentation(
        session_id=session.id,
        case_id=case.id,
        order_index=order_index,
        started_at=now,
        ended_at=None,      # 提交答案时才填
        duration_ms=None,   # 提交答案时才填
    )
    db.add(pres)
    await db.commit()
    await db.refresh(pres)  # 从数据库读回自动生成的 id
    return CaseOpenOut(casePresentationId=pres.id)
