"""
================================================================================
文件作用：建档接口 —— 医生点「开始研究」时，服务器给他建一份档案
================================================================================

这是整个研究流程的第一个接口。医生在知情同意页勾选同意、点下按钮，
浏览器就会调用这里。它做完之后，这个医生才算正式"进入"了实验。

具体做三件事：
  1. 造一个匿名被试（participant）—— 只有一串随机编号，没有姓名手机号
  2. 造一次作答会话（session）—— 之后每个请求都要带着它的编号，服务器靠它认人
  3. 随机抽一套题目顺序 —— 不能所有人都按同一个顺序做题，否则结果会有偏差

--------------------------------------------------------------------------------
本文件的代码块（从上到下）：
--------------------------------------------------------------------------------
  第 1 块  SINGLE_CONDITION    一个常量，标记"本研究只有一种实验条件"
  第 2 块  router              路由器，声明本文件的接口挂在 /api/session 下
  第 3 块  SessionCreatedResponse   定义"返回给浏览器的数据长什么样"
  第 4 块  create_session()    ★ 真正干活的函数，上面说的三件事都在这里
================================================================================
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.db.models import Case, OrderTemplate, Participant, Session, UiEvent
from app.services.randomization import pick_order_template_id


# ── 第 1 块：实验条件常量 ────────────────────────────────────────────────────
# V4: single-condition study. condition field retained on Participant /
# session_started UiEvent for schema continuity but always "single".
#
# 大白话解释：
# 早期版本（V3）把医生随机分成两组，一组看到"风险提示面板"，一组看不到，
# 用来比较两组的差异。V4 取消了这个设计，所有人看到的界面完全一样。
# 数据库里那个 condition 字段没删，是为了老数据还能正常读出来，
# 现在它的值永远是字符串 "single"（意思是"单一条件"）。
SINGLE_CONDITION: str = "single"


# ── 第 2 块：路由器 ──────────────────────────────────────────────────────────
# 创建一个路由器，声明本文件里所有接口的网址都以 /api/session 开头。
# tags 只影响自动生成的接口文档，把相关接口归到一组，方便翻。
router = APIRouter(prefix="/api/session", tags=["session"])


# ── 第 3 块：返回数据的格式 ──────────────────────────────────────────────────
class SessionCreatedResponse(BaseModel):
    """建档成功后返回给浏览器的那一包数据。

    浏览器拿到后会整包存进 localStorage（见前端 lib/store.ts），
    之后每翻一页、每提交一次都要从里面取东西用。
    """

    # 会话编号。★ 最重要的一个字段，之后每个请求都要带上它，服务器靠它认人。
    sessionId: str

    # 被试编号。完成码就是取它的末 8 位大写生成的（AIDR-XXXXXXXX）。
    participantId: str

    # 实验条件，V4 里永远是 "single"。前端拿到也没用，纯粹为了数据完整。
    condition: str

    # 抽中的是第几套题目顺序（1 到 4）。存下来方便事后核对。
    orderTemplateId: int

    # ★ 这个医生接下来要做的 8 道正式题的编号，已经按抽中的顺序排好。
    # 前端就是照着这个列表一道一道往下走的。
    caseOrder: list[str]

    # 练习题的编号。练习题只有一道，所有人都做同一道。
    practiceCaseId: str


# ── 第 4 块：建档函数 ★ 核心 ────────────────────────────────────────────────
# @router.post("") 的意思是：把下面这个函数注册成一个接口，
# 用 POST 方法访问，网址就是路由器的前缀本身，也就是 /api/session。
# response_model 告诉 FastAPI 按第 3 块定义的格式返回，多余字段会被自动过滤掉。
@router.post("", response_model=SessionCreatedResponse)
async def create_session(db: AsyncSession = Depends(db_session)) -> SessionCreatedResponse:
    """POST /api/session —— 给一位医生建档。

    参数 db 不用调用方传，Depends(db_session) 表示"请框架帮我准备一个数据库
    会话塞进来"，用完框架会自动回收。
    """
    # 把缓存的两个函数导进来。写在函数内部而不是文件顶部，是为了避免
    # 文件之间循环引用（A 要 B、B 又要 A，Python 会报错）。
    # get 改名叫 cache_get，是因为 set 会和 Python 内置的 set() 撞名。
    from app.core.cache import get as cache_get, set as cache_set

    # ---- 步骤 1：拿到全部 4 套题目顺序 ----
    # Order templates never change — cache after first DB hit.
    #
    # 大白话：题目顺序是启动时灌进数据库的固定数据，运行中不会变。
    # 所以第一次查完就存进内存，后面 100 个人同时建档都直接读内存，
    # 省掉 100 次数据库查询。
    cache_key_tpl = "templates"          # 给这份缓存起个名字
    templates = cache_get(cache_key_tpl)  # 先看内存里有没有
    if templates is None:                 # 没有 → 说明是第一次，得查数据库
        # select(OrderTemplate) 相当于 SQL 的 SELECT * FROM order_templates。
        # await 表示"等数据库返回，这期间让出去处理别人的请求"。
        # .scalars() 把查询结果从"每行一个元组"变成"每行一个对象"，
        # .all() 取出全部行变成一个列表。
        templates = (await db.execute(select(OrderTemplate))).scalars().all()
        if not templates:
            # 一套顺序都没有 = 启动时的灌数据步骤没跑成功，属于部署事故。
            # 抛 500 让它明确地失败，而不是继续往下跑出更奇怪的错。
            raise HTTPException(500, "No order templates seeded")
        cache_set(cache_key_tpl, templates)  # 存进内存，下次直接用

    # ---- 步骤 2：从 4 套里随机抽一套 ----
    # 先把所有模板的编号收集成一个列表 [1, 2, 3, 4]，交给抽签函数随机挑一个。
    template_id = pick_order_template_id([t.id for t in templates])
    # 再根据抽中的编号，从列表里把那个模板对象本身找出来。
    # next(...) 的意思是"取生成器里的第一个符合条件的元素"。
    template = next(t for t in templates if t.id == template_id)

    # ---- 步骤 3：拿到练习题 ----
    # Practice case ID never changes — cache after first hit.
    # 逻辑和步骤 1 完全一样：先看缓存，没有才查数据库，查完存缓存。
    cache_key_practice = "practice_case"
    practice = cache_get(cache_key_practice)
    if practice is None:
        practice = (
            # where(Case.is_practice.is_(True)) 相当于 SQL 的
            # WHERE is_practice = true，即"只要练习题那一行"。
            await db.execute(select(Case).where(Case.is_practice.is_(True)))
        ).scalars().first()   # .first() 取第一行；没有就返回 None
        if practice is None:
            raise HTTPException(500, "Practice case missing")
        cache_set(cache_key_practice, practice)

    # 把常量取个短名字，下面要用两次。
    condition = SINGLE_CONDITION

    # ---- 步骤 4：新建被试档案 ----
    # 此刻这份档案里几乎是空的：只有一个自动生成的随机编号和抽中的题目顺序。
    # 科室、职级这些要等医生填完前测问卷才会补上（见 api/survey.py）。
    participant = Participant(condition=condition, order_template_id=template_id)
    db.add(participant)   # 把它放进"待写入"的暂存区，此时还没进数据库
    # flush 的意思是"把暂存区的内容发给数据库，但先别正式确认（commit）"。
    # 必须这么做，因为下一行要用 participant.id，而这个编号是数据库生成的，
    # 不 flush 就拿不到。
    await db.flush()

    # ---- 步骤 5：新建作答会话 ----
    # 会话通过 participant_id 关联到刚才那份档案。
    session_row = Session(participant_id=participant.id)
    db.add(session_row)
    await db.flush()   # 同理，为了拿到 session_row.id

    # ---- 步骤 6：记一条"会话开始"的行为埋点 ----
    # 这条记录本身没什么用，但它是这位医生行为时间线的起点，
    # 事后分析"他从进来到交卷一共花了多久"要用到。
    db.add(
        UiEvent(
            session_id=session_row.id,
            event_type="session_started",   # 事件类型，字符串自己约定
            # payload 是附加信息，存成 JSON，想记什么就记什么
            payload={"condition": condition, "orderTemplateId": template_id},
        )
    )

    # ---- 步骤 7：正式写入数据库 ----
    # ★ commit 才是真正落盘。上面三条记录（被试、会话、埋点）在这一刻
    # 要么一起成功，要么一起失败——不会出现"有被试没会话"的半截数据。
    # 这个特性叫"事务"。
    await db.commit()

    # ---- 步骤 8：把结果返回给浏览器 ----
    # list(template.order) 把数据库里存的题目顺序复制成一个普通列表。
    # 复制一份而不是直接用，是因为 template 是缓存对象，被多个请求共用，
    # 万一哪天有人不小心改了它，会影响到所有人。
    return SessionCreatedResponse(
        sessionId=session_row.id,
        participantId=participant.id,
        condition=condition,
        orderTemplateId=template_id,
        caseOrder=list(template.order),
        practiceCaseId=practice.id,
    )
