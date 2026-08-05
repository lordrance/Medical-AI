"""
================================================================================
文件作用：发题接口 —— 把一道题的内容给浏览器，并记录"这个人开始看这道题了"
================================================================================

医生每翻到一道新题，浏览器就会调这里两次：
    第 1 次  GET  /api/case/{题目编号}   把题目内容取回来显示
    第 2 次  POST /api/case/open         告诉服务器"我开始看这道题了"

第 2 次调用只是为了埋点：它建一条记录并返回编号，之后医生所有的点击行为
都会带上这个编号，这样才知道"展开病历"这个动作是发生在哪道题上的。
★ 所以第 2 次调用失败也不影响答题——前端会照常显示题目、照常能提交。

--------------------------------------------------------------------------------
本文件的代码块（从上到下）：
--------------------------------------------------------------------------------
  第 1 块  导入区
  第 2 块  router                路由器，接口挂在 /api/case 下
  第 3 块  设计说明注释          ★ 全项目最重要的一条研究规矩写在这里
  第 4 块  get_case()            取题目内容
  第 5 块  CaseOpenIn / Out      第 6 块接口的输入输出格式
  第 6 块  open_case()           记录"开始看这道题"（外壳，负责加锁）
  第 7 块  _open_presentation()  真正干活的部分（在锁里面执行）
================================================================================
"""

# ── 第 1 块：导入区 ──────────────────────────────────────────────────────────
from __future__ import annotations

# datetime：日期时间类型；timezone：时区。
# 全项目统一用 UTC 时间存储，显示时再转成本地时间。
from datetime import datetime, timezone

# Query：声明"这个参数从网址的问号后面取"（如 ?sessionId=abc）。
from fastapi import APIRouter, Depends, HTTPException, Query

# Field：给字段加额外约束（比如"必须大于等于 -1"）。
from pydantic import BaseModel, Field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session

# session_write_lock：给同一个人的写操作排队的锁，见 db/locks.py。
from app.db.locks import session_write_lock

from app.db.models import Action, Case, CasePresentation, Participant, Session

# CasePayload：发给前端的题目格式（只含医生该看到的字段）。
from app.schemas.case import CasePayload, CaseResponse


# ── 第 2 块：路由器 ──────────────────────────────────────────────────────────
router = APIRouter(prefix="/api/case", tags=["case"])


# ── 第 3 块：设计说明 ★ 全项目最重要的规矩 ──────────────────────────────────
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
# ────────────────────────────────────────────────────────────────────────────
# 大白话解释（这条规矩如果被破坏，整个研究就白做了）：
#
# 同一道题，每个医生看到的 AI 草稿必须一模一样，一个字都不能差。
#
# 为什么：这个研究要测的是"医生怎么审核 AI 写的东西"。如果每个医生看到的
# AI 文本都不一样，那当甲医生原样发送、乙医生大改特改时，你根本分不清是
# "两人态度不同"还是"他俩看到的文本本来就一好一坏"。AI 文本就成了一个
# 不受控的变量，任何结论都站不住脚。
#
# 所以医生端**绝对不会**实时调用 AI 生成文本。这里只是把 cases.json 里
# 预先写死的 ai_draft 原样返回。
# （backend/tests/test_llm.py 有一个专门的测试守着这条规矩：它会检查
#  加载题目的过程中一次 AI 调用都没发生。）
#
# 另外：V3 版本有个"风险提示面板"，会给医生显示 AI 用了哪些病历事实、
# 有什么风险点。V4 改成单一条件后不再显示，但这些数据仍然存在数据库里
# 并会被导出，作为研究的元数据保留。
# ────────────────────────────────────────────────────────────────────────────


# ── 第 4 块：取题目内容 ──────────────────────────────────────────────────────
# 网址里的 {case_id} 是可变部分，比如 /api/case/case_03。
# FastAPI 会自动把它填进下面同名的参数。
@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: str,                              # 从网址路径里取
    sessionId: str = Query(...),               # 从网址问号后面取，(...) 表示必填
    db: AsyncSession = Depends(db_session),    # 框架自动准备的数据库会话
) -> CaseResponse:
    """GET /api/case/{题目编号}?sessionId=xxx —— 取一道题的内容。

    这是全系统调用最频繁的接口：每位医生要调 9 次（1 道练习 + 8 道正式）。
    """
    # ---- 步骤 1：验明正身 ----
    # db.get(表, 主键) 相当于 SQL 的 SELECT * FROM sessions WHERE id = ?。
    session = await db.get(Session, sessionId)
    if session is None:
        # 找不到这个会话 = 编号是编的，或者数据库被重置过。
        # ★ 前端收到这个 404 会自动清空本地状态、把医生送回知情同意页
        #   重新开始（见前端 lib/api/client.ts 的 isSessionInvalid）。
        #   不这么做的话，他刷新一百次都是同样的 404，永远卡在这里。
        raise HTTPException(404, "Unknown session")

    # 再确认这个会话背后的被试档案也在。理论上不会缺，属于防御性检查。
    participant = await db.get(Participant, session.participant_id)
    if participant is None:
        raise HTTPException(404, "Unknown participant")

    # ---- 步骤 2：先查内存缓存 ----
    # Cases are read-only seed data — serve from memory when cached.
    #
    # 大白话：题目内容是启动时灌进去的固定数据，运行中不会变。
    # 第一次查完就存内存，之后直接读内存。100 个人同时答题时，
    # 这一步省掉了将近 900 次数据库查询。
    from app.core.cache import get as cache_get, set as cache_set

    # 缓存的名字要能区分不同题目，所以拼上题号：如 "case:case_03"。
    cache_key = f"case:{case_id}"
    cached = cache_get(cache_key)
    if cached is not None:
        # 内存里有，直接返回，连数据库都不用碰。
        return CaseResponse(case=cached)

    # ---- 步骤 3：缓存没有，查数据库 ----
    case = await db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")

    # ---- 步骤 4：挑出能给医生看的字段 ----
    # ★ 这一步是安全设计的关键。
    # 数据库里的 case 对象还包含 gold_action（标准答案）、defect_present
    # （这题有没有埋错）、defect_type（埋的什么错）等字段。这些**绝对不能**
    # 发给前端——医生打开浏览器的开发者工具就能看到网络请求的内容，
    # 一看就知道答案了。
    #
    # CasePayload 这个类里压根就没定义那几个字段（见 schemas/case.py），
    # 所以就算这里手滑写错，也不可能把答案泄露出去。
    payload = CasePayload(
        id=case.id,
        isPractice=case.is_practice,
        riskLevel=case.risk_level,          # 高/低风险，目前前端不显示
        patientMessage=case.patient_message,  # 患者发来的消息
        chartSnapshot=case.chart_snapshot,    # 病历摘要
        aiDraft=case.ai_draft,                # ★ AI 起草的回复（写死的，见第 3 块）
        guardrail=None,                       # V4 不显示风险提示面板
    )

    # 存进缓存，下一个人来取同一道题就走步骤 2 的快速通道了。
    cache_set(cache_key, payload)
    return CaseResponse(case=payload)


# ── 第 5 块：/api/case/open 的输入输出格式 ──────────────────────────────────
class CaseOpenIn(BaseModel):
    """前端调 /api/case/open 时发上来的数据。"""

    sessionId: str
    caseId: str
    # 这是第几道题。
    # Field(..., ge=-1) 的意思：必填（...），且必须大于等于 -1（ge = 大于等于）。
    # 0~7 是 8 道正式题，-1 专门表示练习题。
    orderIndex: int = Field(..., ge=-1)


class CaseOpenOut(BaseModel):
    """返回给前端的数据：只有一个编号。"""

    # 前端拿到后存起来，之后每条埋点都带上它，用来标明"这个动作发生在哪道题上"。
    casePresentationId: str


# ── 第 6 块：记录"开始看这道题"（外壳，负责加锁）────────────────────────────
@router.post("/open", response_model=CaseOpenOut)
async def open_case(
    body: CaseOpenIn,
    db: AsyncSession = Depends(db_session),
) -> CaseOpenOut:
    """Create or return an in-progress CasePresentation for UI event correlation.

    POST /api/case/open —— 建一条"某人开始看某题"的记录，返回它的编号。

    ★ 这个接口失败不影响答题。前端把它当成纯埋点，即使它返回 500，
      题目照样显示、答案照样能提交（见前端 app/case/[order]/page.tsx，
      它把这个请求单独放在一个 try/catch 里，失败就当没这回事）。
    """
    # 老规矩，先验明正身。
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
    # ────────────────────────────────────────────────────────────────────
    # 大白话：为什么这里要加锁？
    #
    # 同一道题的两次"打开"有可能同时发生：网络卡了浏览器自动重发、
    # 医生快速地前后翻页、页面刷新……
    #
    # 下面 _open_presentation 的逻辑是"先查有没有 → 没有就新建"。
    # 两个请求同时跑的话，会变成：
    #     请求A 查：没有   请求B 查：没有
    #     请求A 建一条     请求B 又建一条    ← 重复了
    #
    # 生产数据库在加这把锁之前，已经因此积累了 23 组重复记录。
    #
    # 这把锁是按 sessionId 加的，只挡"同一个人自己的请求"，
    # 不同医生之间完全不互相等待，所以 100 人同时在线也没有性能问题。
    # ────────────────────────────────────────────────────────────────────
    async with session_write_lock(db, session.id):
        # 锁拿到手了，进去干活。出了这个 with 块锁自动释放。
        return await _open_presentation(db, session, case, body.orderIndex)


# ── 第 7 块：真正干活的部分 ──────────────────────────────────────────────────
# 函数名前面的下划线是 Python 的约定，表示"这是内部函数，别从外面直接调"。
async def _open_presentation(
    db: AsyncSession, session: Session, case: Case, order_index: int
) -> CaseOpenOut:
    """★ 必须在 session_write_lock 里面调用，否则锁就白加了。"""

    # ---- 步骤 1：找找有没有可以复用的记录 ----
    # 要找的是"这个人的这道题，已经打开过、但还没提交答案"的那条记录。
    # 找到了就复用（说明是刷新页面或重新打开），不要新建。
    reuse_stmt = (
        select(CasePresentation)
        # outerjoin = 左连接：把 actions 表接过来，接不上的行也保留。
        # 目的是让下面能判断"这条记录有没有对应的作答"。
        .outerjoin(Action, Action.case_presentation_id == CasePresentation.id)
        .where(
            CasePresentation.session_id == session.id,   # 是这个人的
            CasePresentation.case_id == case.id,         # 是这道题的
            # ★ 关键条件：接过来的 actions 那边是空的，
            #   说明这道题还没提交答案，是"进行中"的状态。
            Action.id.is_(None),
        )
        # 按开始时间排序。万一有多条（历史遗留的重复数据），
        # 每次都取最早那条，保证结果稳定可复现。
        .order_by(CasePresentation.started_at.asc())
        .limit(1)   # 只要一条
    )
    existing = (await db.execute(reuse_stmt)).scalars().first()

    if existing is not None:
        # 找到了 → 更新一下题号（可能医生是从别的顺序进来的），返回原编号。
        existing.order_index = order_index
        await db.commit()
        return CaseOpenOut(casePresentationId=existing.id)

    # ---- 步骤 2：没有可复用的，新建一条 ----
    # datetime.now(timezone.utc) 取当前的 UTC 时间。
    # 一定要带时区，不带的话不同服务器/不同时区跑出来的数据没法比较。
    now = datetime.now(timezone.utc)
    pres = CasePresentation(
        session_id=session.id,
        case_id=case.id,
        order_index=order_index,
        started_at=now,
        ended_at=None,      # 结束时间等提交答案时才填（见 api/action.py）
        duration_ms=None,   # 用时同理
    )
    db.add(pres)
    await db.commit()

    # refresh 的意思是"从数据库把这条记录重新读一遍"。
    # 需要它是因为 id 是数据库自动生成的，不读回来就拿不到。
    await db.refresh(pres)
    return CaseOpenOut(casePresentationId=pres.id)
