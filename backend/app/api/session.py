"""建档接口：医生点「开始研究」时调用的第一个接口。

做三件事：
  1. 生成一个匿名被试（participant），不含任何真实身份信息；
  2. 生成一次作答会话（session），后续所有请求都带着这个 sessionId；
  3. 随机抽一套题目顺序，避免所有人都按同一顺序看题（顺序会影响作答）。

返回的 caseOrder 就是这个人接下来要做的 8 道题的 ID 列表。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.db.models import Case, OrderTemplate, Participant, Session, UiEvent
from app.services.randomization import pick_order_template_id

# V4: single-condition study. condition field retained on Participant /
# session_started UiEvent for schema continuity but always "single".
#
# 中文：V3 时代有「实验组 / 对照组」两种条件，V4 改成单一条件（所有人看到的
# 界面完全一样）。数据库字段保留是为了老数据还能读，值恒定为 "single"。
SINGLE_CONDITION: str = "single"

router = APIRouter(prefix="/api/session", tags=["session"])


class SessionCreatedResponse(BaseModel):
    """返回给前端的建档结果。前端会把这一整包存进浏览器，之后每一步都要用。"""

    sessionId: str        # 会话 ID，后续每个请求都要带
    participantId: str    # 被试 ID，完成码就是从它末 8 位生成的
    condition: str        # 恒为 "single"
    orderTemplateId: int  # 抽到的是第几套题目顺序（1~4）
    caseOrder: list[str]  # 8 道正式题的 ID，按抽到的顺序排列
    practiceCaseId: str   # 练习题的 ID


@router.post("", response_model=SessionCreatedResponse)
async def create_session(db: AsyncSession = Depends(db_session)) -> SessionCreatedResponse:
    """POST /api/session —— 建档。"""
    from app.core.cache import get as cache_get, set as cache_set

    # Order templates never change — cache after first DB hit.
    #
    # 中文：题目顺序模板是启动时灌进数据库的固定数据，运行中不会变。
    # 第一次查完就存进内存，之后 100 个人同时建档也不用反复查库。
    cache_key_tpl = "templates"
    templates = cache_get(cache_key_tpl)
    if templates is None:
        templates = (await db.execute(select(OrderTemplate))).scalars().all()
        if not templates:
            # 数据库里一套顺序模板都没有 = 没执行过 seed，属于部署事故。
            raise HTTPException(500, "No order templates seeded")
        cache_set(cache_key_tpl, templates)

    # 从 4 套顺序里随机抽一套，这就是这个人的答题顺序。
    template_id = pick_order_template_id([t.id for t in templates])
    template = next(t for t in templates if t.id == template_id)

    # Practice case ID never changes — cache after first hit.
    # 中文：练习题只有一道，同样缓存起来。
    cache_key_practice = "practice_case"
    practice = cache_get(cache_key_practice)
    if practice is None:
        practice = (
            await db.execute(select(Case).where(Case.is_practice.is_(True)))
        ).scalars().first()
        if practice is None:
            raise HTTPException(500, "Practice case missing")
        cache_set(cache_key_practice, practice)

    condition = SINGLE_CONDITION

    # 建被试档案。此时除了「抽到哪套顺序」之外没有任何信息，
    # 科室/职级等要等前测问卷提交后才会填进来。
    participant = Participant(condition=condition, order_template_id=template_id)
    db.add(participant)
    await db.flush()  # flush 让数据库生成 participant.id，但还没提交事务

    # 建会话。一个被试理论上可以有多个会话，实际用下来是一对一。
    session_row = Session(participant_id=participant.id)
    db.add(session_row)
    await db.flush()

    # 埋一条「会话开始」事件，用于后续分析作答时间线。
    db.add(
        UiEvent(
            session_id=session_row.id,
            event_type="session_started",
            payload={"condition": condition, "orderTemplateId": template_id},
        )
    )
    # 到这里才真正写进数据库。上面三条记录要么一起成功，要么一起失败。
    await db.commit()

    return SessionCreatedResponse(
        sessionId=session_row.id,
        participantId=participant.id,
        condition=condition,
        orderTemplateId=template_id,
        caseOrder=list(template.order),
        practiceCaseId=practice.id,
    )
