"""行为埋点接口：记录医生在页面上的一举一动。

前端会在这些时刻打过来：展开病历、点开 AI 草稿、切换到别的 App、
点了某个处理选项、开始编辑回复……每条都写一行 ui_events。
生产库里现在有 2387 条，是分析「医生是怎么看的」的原始素材。

★ 最重要的设计原则：这个接口永远不向前端报错。
埋点失败只是少一条分析数据，绝不能因此让医生的答题界面弹错误。
所以整个函数体被 try/except 包住，出错只写服务器日志。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.db.models import UiEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ui-event", tags=["ui-event"])


class UiEventIn(BaseModel):
    """前端上报的一条埋点。"""

    sessionId: str                        # 谁
    casePresentationId: str | None = None # 在哪道题上（练习/正式题都有，前测后测没有）
    eventType: str                        # 什么事件，如 "chart_expanded" "page_blur"
    payload: dict[str, Any] | None = None # 事件附带的信息，如 {"caseId": "case_03"}
    clientTs: datetime | None = None      # 浏览器本地时间（服务器也会记自己的时间）


@router.post("")
async def submit_event(
    body: UiEventIn, db: AsyncSession = Depends(db_session)
) -> dict:
    """POST /api/ui-event —— 记录一条行为埋点。"""
    # fire-and-forget semantics: never raise to client even on failure
    #
    # 中文：「发了就不管」语义。下面整段无论出什么错都吞掉，
    # 因为前端是用 sendBeacon / keepalive fetch 打过来的，本来就不看返回值；
    # 而一旦这里抛异常，FastAPI 会返回 500，前端控制台报红，
    # 万一将来有人改成阻塞式调用就会直接卡住答题流程。
    try:
        db.add(
            UiEvent(
                session_id=body.sessionId,
                case_presentation_id=body.casePresentationId,
                event_type=body.eventType,
                payload=body.payload,
                client_ts=body.clientTs,
            )
        )
        await db.commit()
    except Exception:
        # 回滚这次没写成的事务，否则这条数据库连接会一直卡在出错状态。
        await db.rollback()
        logger.warning(
            "ui_event persistence failed (silently dropped)",
            extra={
                "sessionId": body.sessionId,
                "casePresentationId": body.casePresentationId,
                "eventType": body.eventType,
            },
            exc_info=True,
        )
    # 不管成没成功都回 ok，前端不需要知道埋点有没有落库。
    return {"ok": True}
