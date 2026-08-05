"""
================================================================================
文件作用：行为埋点接口 —— 记录医生在页面上的一举一动
================================================================================

医生在答题时，前端会不停地往这里发小数据包，记录他做了什么：
    展开了病历、点开了 AI 草稿、切到微信去了、又切回来了、
    选了某个处理方式、开始在编辑框里打字……

每来一条就往 ui_events 表里写一行。生产库里现在有 2387 行，
这些是分析"医生到底有没有认真核对"的原始素材。

★ 本文件最重要的一条规矩：这个接口永远不向前端报错。
   埋点失败只是少一条分析数据，绝不能因此让医生的答题界面弹出错误。
   所以整个函数体被 try/except 包住，出错只写服务器日志，对外照样回 ok。

--------------------------------------------------------------------------------
本文件的代码块（从上到下）：
--------------------------------------------------------------------------------
  第 1 块  导入区            搬工具
  第 2 块  logger            日志记录器，出错时往服务器日志里写
  第 3 块  router            路由器，接口挂在 /api/ui-event
  第 4 块  UiEventIn         定义"前端发上来的数据长什么样"
  第 5 块  submit_event()    ★ 干活的函数：写一行埋点，出错就吞掉
================================================================================
"""

# ── 第 1 块：导入区 ──────────────────────────────────────────────────────────
from __future__ import annotations

# Python 自带的日志模块。
import logging

# datetime：日期时间类型。前端会传一个浏览器本地时间戳过来。
from datetime import datetime

# Any 表示"任意类型"。埋点的附加信息什么都可能有，所以用它。
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.db.models import UiEvent   # ui_events 这张表


# ── 第 2 块：日志记录器 ──────────────────────────────────────────────────────
# __name__ 是当前模块的名字（这里是 "app.api.ui_event"）。
# 用它当日志名字的好处是：看服务器日志时一眼就知道这条是哪个文件打的。
logger = logging.getLogger(__name__)


# ── 第 3 块：路由器 ──────────────────────────────────────────────────────────
router = APIRouter(prefix="/api/ui-event", tags=["ui-event"])


# ── 第 4 块：前端发上来的数据格式 ────────────────────────────────────────────
class UiEventIn(BaseModel):
    """一条埋点。前端每次只发一条。"""

    # 谁。必填。
    sessionId: str

    # 在哪道题上发生的。
    # 类型写 `str | None = None` 表示"可以是字符串，也可以没有，默认没有"。
    # 为什么可以没有：填前测/后测问卷时的事件不属于任何一道题。
    casePresentationId: str | None = None

    # 什么事件。字符串，取值由前后端自己约定，比如：
    #   "case_view_start"        开始看这道题
    #   "chart_expanded"         展开了病历
    #   "page_blur"              切走了
    #   "action_button_selected" 选了某个处理方式
    eventType: str

    # 事件的附加信息，存成 JSON。比如 {"caseId": "case_03"}。
    # 想记什么就记什么，不用改数据库表结构。
    payload: dict[str, Any] | None = None

    # 浏览器本地时间。服务器也会记自己的时间（见 models.py 的 server_ts）。
    # 两个都记是因为浏览器时间可能不准（用户改过系统时间、时区不对），
    # 但它能反映"用户感知的间隔"，两者结合分析更可靠。
    clientTs: datetime | None = None


# ── 第 5 块：写埋点的函数 ────────────────────────────────────────────────────
@router.post("")
async def submit_event(
    body: UiEventIn, db: AsyncSession = Depends(db_session)
) -> dict:
    """POST /api/ui-event —— 记录一条行为埋点。

    参数 body 由 FastAPI 自动填充：它会把前端发来的 JSON 按第 4 块的格式
    解析并检查，格式不对直接返回 422，根本进不到这个函数里。
    """
    # fire-and-forget semantics: never raise to client even on failure
    #
    # 大白话：「发了就不管」。下面这段无论出什么错都吞掉，原因有两个：
    #   1. 前端是用 sendBeacon 发的（见前端 lib/logger.ts），
    #      那个方法本来就不看返回值，报错了也没人接。
    #   2. 万一将来有人把它改成会阻塞界面的写法，一旦这里抛异常，
    #      医生的答题流程就会被一条无关紧要的埋点卡住。
    try:
        # 造一行 UiEvent 记录，放进待写入的暂存区。
        db.add(
            UiEvent(
                session_id=body.sessionId,
                case_presentation_id=body.casePresentationId,
                event_type=body.eventType,
                payload=body.payload,
                client_ts=body.clientTs,
            )
        )
        # 正式写进数据库。
        await db.commit()
    except Exception:
        # 走到这里说明写失败了（比如 sessionId 是假的、数据库连不上）。
        #
        # ★ rollback 必须做：不回滚的话，这条数据库连接会带着一个失败的
        # 事务被还回连接池，下一个拿到它的请求会莫名其妙地一起失败。
        await db.rollback()

        # 把详细情况写进服务器日志，方便事后排查。
        # exc_info=True 表示把完整的错误堆栈也一起记下来。
        logger.warning(
            "ui_event persistence failed (silently dropped)",
            extra={
                "sessionId": body.sessionId,
                "casePresentationId": body.casePresentationId,
                "eventType": body.eventType,
            },
            exc_info=True,
        )

    # ★ 注意这一行在 try/except 外面：不管上面成没成功，都返回 ok。
    # 前端不需要知道埋点有没有落库，它也不会看。
    return {"ok": True}
