"""
================================================================================
文件作用：★ 全系统最核心的接口 —— 医生提交一道题的作答
================================================================================

医生在一道题上做完这一串动作后，前端把它们打包成一个请求发到这里：
  1. 看患者消息、展开病历、读 AI 草稿
  2. 选一个处理方式（原样发送 / 修改后发 / 弃用重写 / 上报）
  3. （如果选了修改或重写）在编辑框里写下最终回复
  4. 选一个"为什么这么选"的理由
  5. 答两道小量表（对判断有多大信心、AI 草稿有多大帮助）

同时前端还偷偷带上了一大包行为数据：这道题看了多久、展开过病历没有、
在草稿区滚动到了哪里、敲了多少下键盘……

这个接口会往三张表里写：
  case_presentations —— 更新这道题的起止时间和用时
  actions            —— ★ 医生的选择、最终文本、编辑距离、行为指标（研究核心数据）
  case_surveys       —— 那两道小量表的分数

★ 关键特性「幂等」：同一道题重复提交，只保留**第一次**的答案，后面的请求
  原样返回第一次的结果。医生网络卡了重复点提交也不会出错、不会产生重复数据。

--------------------------------------------------------------------------------
本文件的代码块（从上到下）：
--------------------------------------------------------------------------------
  第 1 块  router                        路由器，接口挂在 /api/action
  第 2 块  _CHOICE_TO_PDF                四种处理方式 → 问卷编号 1/2/3/4 的对照表
  第 3 块  TimingIn                      前端传来的"这题花了多久"
  第 4 块  QuickCaseSurveyIn             那两道小量表的分数
  第 5 块  ClientStatsIn                 一大包行为数据
  第 6 块  ActionIn                      ★ 整个请求的完整格式（含两条校验规则）
  第 7 块  ActionResponse                返回给前端的数据
  第 8 块  _to_dt()                      小工具：毫秒时间戳 → 日期时间
  第 9 块  build_pdf_autolog_client_stats()  把行为数据翻译成问卷规定的变量名
  第10 块  submit_action()               ★ 接口入口（负责验身 + 加锁）
  第11 块  _persist_action()             ★ 真正落库的五个步骤（在锁里面跑）
================================================================================
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


# ── 第 1 块：路由器 ──────────────────────────────────────────────────────────
router = APIRouter(prefix="/api/action", tags=["action"])


# ── 第 2 块：处理方式 → 问卷编号的对照表 ────────────────────────────────────
# 把四个处理方式映射成问卷 PDF 里规定的编号（1/2/3/4），
# 这样导出的数据能直接对上论文里的编码表。
#
# 大白话：论文的编码表里写的是"1 = 直接发送、2 = 编辑后发送……"，
# 而代码里用的是 "send_as_is" 这种英文名。这张表就是两者的翻译对照，
# 导出 CSV 时数字列可以直接喂给 SPSS，不用再人工换算。
_CHOICE_TO_PDF: dict[SelectedAction, int] = {
    SelectedAction.send_as_is: 1,           # 原样发送
    SelectedAction.edit_then_send: 2,       # 修改后发送
    SelectedAction.discard_and_rewrite: 3,  # 弃用并重写
    SelectedAction.escalate: 4,             # 上报 / 转诊
}


# ── 第 3 块：这道题花了多久 ─────────────────────────────────────────────────
class TimingIn(BaseModel):
    """前端记录的答题耗时。"""

    # 开始时间。单位是"从 1970 年至今的毫秒数"（叫 epoch 毫秒），
    # 这是浏览器里 Date.now() 的返回值，传数字比传字符串省事也不会有时区问题。
    startedAt: int  # epoch ms (client clock; server records own ts too)

    # 结束时间，同上。
    endedAt: int

    # 总时长（毫秒）。
    # Field(ge=0) 表示"必须大于等于 0"（ge = greater or equal）。
    # 加这个约束是防止浏览器时钟被改动后算出负数，那样统计就废了。
    durationMs: int = Field(ge=0)


# ── 第 4 块：每题后面的两道小量表 ───────────────────────────────────────────
class QuickCaseSurveyIn(BaseModel):
    """案例内嵌入式量表（问卷 7.0）：判断信心、AI 起草帮助感。"""

    # 「我对自己刚才作出的判断有信心」，1~5 分。
    # ge=1, le=5 表示"必须在 1 到 5 之间"（le = less or equal）。
    # 超出范围前端就传不进来，会被挡在门外返回 422。
    caseDecisionConfidence: int = Field(ge=1, le=5)

    # 「AI 起草的内容在本案例中是有帮助的」，1~5 分。
    caseDraftHelpfulness: int = Field(ge=1, le=5)


# ── 第 5 块：行为数据 ★ 这是研究的隐藏金矿 ──────────────────────────────────
class ClientStatsIn(BaseModel):
    """前端上报的原始过程量；落库时仅抽取用于计算 PDF 第五节 log_* 的字段。

    大白话：这些数据回答的是"医生到底有没有认真看"这个问题。
    医生自己说"我认真核对了"，但如果数据显示他 8 秒就交卷、病历一次都没展开、
    草稿只滚动到 20% 就停了——那说明他其实是扫一眼就点了发送。
    这类客观行为证据比自我报告可靠得多。

    全部字段都是可选的（有默认值）。万一前端因为老浏览器不支持某个 API
    而收集不到，也不能因此让整个提交失败。
    """

    # 从看到题目到第一次点击隔了多久（毫秒）。
    # 可以是 None —— 表示他压根没点过任何东西就直接提交了。
    timeToFirstClickMs: int | None = None

    # 各个区域分别被点了几次，形如 {"chart_panel": 3, "ai_draft_panel": 1}。
    # default_factory=dict 表示"默认值是一个新的空字典"。
    # ★ 这里不能写 = {}，因为 Python 的默认参数是所有实例共享同一个对象，
    #   一个人改了会影响到所有人。default_factory 每次都造一个新的。
    panelClickCounts: dict[str, int] = Field(default_factory=dict)

    # 在编辑框里敲了几下键盘。0 = 一个字没改。
    editKeystrokes: int = 0

    # 打开编辑框几次。
    editBoxOpenedCount: int = 0

    # 更细的交互指标，比如"展开病历几次""有没有真的看过病历"。
    interactionMetrics: dict[str, object] | None = None

    # AI 草稿那块区域滚动了几次。
    draftScrollEventCount: int = 0

    # ★ 最深滚到了草稿的百分之几（0.0 ~ 1.0）。
    # 只滚到 0.2 说明后面 80% 的内容根本没进入视野，等于没看。
    draftScrollMaxDepthRatio: float = 0.0

    # 在草稿区停留了多久（毫秒）。
    draftSectionDwellMs: int = 0


# ── 第 6 块：整个请求的格式 ★ ───────────────────────────────────────────────
class ActionIn(BaseModel):
    """前端提交上来的完整作答包。

    FastAPI 会自动按这个格式解析和检查前端发来的 JSON。
    任何一项不合规都直接返回 422，根本进不到接口函数里——
    所以数据库里的每一条作答记录都是格式完整的。
    """

    sessionId: str        # 谁
    caseId: str           # 哪道题
    orderIndex: int       # 这是第几题（0~7 是正式题，-1 是练习题）
    isPractice: bool = False  # 是不是练习题

    # ★ 因变量：四选一的处理方式。这是整个实验要观测的核心行为。
    selectedAction: SelectedAction

    # 医生最终定稿的回复全文。
    finalReplyText: str

    # 下面两个只在选「上报」时才有值。
    escalateSubtype: EscalateSubtype | None = None  # 上报的子类型（紧急面诊/电话联系/其他）
    escalateReason: str | None = None               # 上报理由（必填，见下面的校验）

    # 为什么这么选。是个枚举，前端会根据处理方式过滤可选项。
    caseActionReasonCode: ActionReasonCode
    # 选「其他」时的补充说明（必填，见下面的校验）。
    caseActionReasonText: str | None = None

    quickSurvey: QuickCaseSurveyIn   # 两道小量表
    timing: TimingIn                 # 耗时
    clientStats: ClientStatsIn | None = None  # 行为数据（可以没有，没有就当全 0）

    # @model_validator(mode="after") 表示：等所有字段都各自检查完之后，
    # 再跑这个"整体检查"。因为它要同时看两个字段的关系，单个字段检查做不到。
    @model_validator(mode="after")
    def _escalate_requires_reason(self) -> ActionIn:
        """选了「上报」就必须写理由，否则这条数据没有分析价值。"""
        if self.selectedAction == SelectedAction.escalate:
            # (self.escalateReason or "") 的意思是"是 None 就当成空字符串"，
            # 这样后面直接 .strip() 不会因为 None 而报错。
            # .strip() 去掉首尾空白，防止医生打几个空格就蒙混过关。
            if not (self.escalateReason or "").strip():
                # 抛 ValueError，Pydantic 会把它转成 422 返回给前端。
                raise ValueError("escalateReason is required when escalating")
        return self  # 校验器必须把对象返回回去

    @model_validator(mode="after")
    def _other_reason_requires_text(self) -> ActionIn:
        """理由选了「其他」就必须写清楚是什么，否则等于没选。"""
        if self.caseActionReasonCode == ActionReasonCode.other:
            if not (self.caseActionReasonText or "").strip():
                raise ValueError("caseActionReasonText is required when reason is other")
        return self


# ── 第 7 块：返回给前端的数据 ───────────────────────────────────────────────
class ActionResponse(BaseModel):
    ok: bool                    # 固定 true
    casePresentationId: str     # 这次作答对应的记录编号
    editDistance: int           # 医生把 AI 草稿改了多少个字符


# ── 第 8 块：小工具 —— 毫秒时间戳转日期时间 ─────────────────────────────────
def _to_dt(ms: int) -> datetime:
    """把浏览器传来的毫秒时间戳，转成带时区的日期时间对象。

    ms / 1000.0 是因为 Python 的 fromtimestamp 要的是"秒"，而浏览器给的是"毫秒"。
    tz=timezone.utc 表示按 UTC 时区解释。★ 一定要带时区：不带的话，
    不同服务器、不同时区跑出来的时间没法互相比较，数据就乱了。
    """
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


# ── 第 9 块：把行为数据翻译成问卷规定的变量名 ───────────────────────────────
def build_pdf_autolog_client_stats(
    body: ActionIn, incoming: dict[str, Any] | None
) -> dict[str, Any]:
    """问卷 PDF 第五节「后台自动记录」：仅写入与 PDF 编码词一致的 log_* 键（不含派生/人工编码）。

    大白话：前端收集的数据用的是它自己的命名（editKeystrokes 之类），
    而论文的编码表用的是另一套命名（全部以 log_ 开头）。这个函数负责翻译，
    翻译后的结果存进 actions.client_stats 字段。

    ★ 好处：你导出 CSV 后，列名能直接对上论文编码表，不用再手工换算。
    ★ 所以这些键名不要随便改，改了就和研究工具对不上了。
    """
    # incoming 可能是 None（前端没传行为数据），统一成空字典好处理。
    raw = incoming or {}
    t = body.timing  # 取个短名字，下面要用

    # 先建一个字典，装上肯定能算出来的几项。
    out: dict[str, Any] = {
        # 这道题看了多少秒。除以 1000 把毫秒变成秒，保留 3 位小数。
        "log_case_review_time": round(t.durationMs / 1000.0, 3),
        # ↓ 下面四个是「独热编码」：选了哪个那个就是 1，其余都是 0。
        #   看着重复，但统计软件（SPSS / R）做回归时直接吃这种 0/1 列最省事，
        #   不用再手工转换成哑变量。
        "log_send_as_is": 1 if body.selectedAction == SelectedAction.send_as_is else 0,
        "log_edit_then_send": (1 if body.selectedAction == SelectedAction.edit_then_send else 0),
        "log_discard_rewrite": (
            1 if body.selectedAction == SelectedAction.discard_and_rewrite else 0
        ),
        "log_escalate": 1 if body.selectedAction == SelectedAction.escalate else 0,
    }

    # 「从看到题到第一次点击」的时间。可能没有（他没点过任何东西），
    # 那就存 None，事后分析时能明确区分"没点"和"点得很快"。
    ttfc = raw.get("timeToFirstClickMs")
    out["log_time_to_first_action"] = round(float(ttfc) / 1000.0, 3) if ttfc is not None else None

    cs = body.clientStats
    if cs is not None:
        # ---- 前端有传行为数据 ----

        # 编辑动作总数 = 敲键次数 + 打开编辑框次数。
        out["log_edit_actions"] = cs.editKeystrokes + cs.editBoxOpenedCount

        # interactionMetrics 可能是 None，统一成空字典。
        im = cs.interactionMetrics or {}
        # bool(...) 把可能是 None / 缺失的值统一转成 True 或 False。
        chart_ok = bool(im.get("chartEverExpandedToView"))       # 真的看过病历吗
        guard_ok = bool(im.get("guardrailEverExpandedToView"))   # V4 恒为 False

        # ★ 有没有打开过任何"信息来源面板"（病历或风险提示）。
        # 这一项为 0 意味着：医生没看任何佐证材料就作出了判断。
        out["log_source_panel_open"] = int(chart_ok or guard_ok)
        out["log_help_risk_panel"] = int(guard_ok)

        # 在"病历"和"草稿"之间来回切换了几次。切换越多说明对照得越仔细。
        # `or 0` 是防止值是 None 时 int() 报错。
        out["log_toggle_draft_source"] = int(im.get("draftSourceSwitchCount") or 0)

        # 核对性点击的总次数（四个面板加起来）。
        # clicks.get(键, 0) 表示"取不到就当 0"，避免 KeyError。
        clicks = cs.panelClickCounts or {}
        out["log_verification_clicks"] = int(
            clicks.get("chart_panel", 0)
            + clicks.get("guardrail_panel", 0)
            + clicks.get("facts_panel", 0)
            + clicks.get("risk_panel", 0)
        )

        # 阅读草稿的深度指标，打包成一个小字典存进去。
        out["log_scroll_dwell_draft"] = {
            "section_dwell_sec": round(cs.draftSectionDwellMs / 1000.0, 4),  # 停留秒数
            "max_depth_ratio": float(cs.draftScrollMaxDepthRatio),           # 最深滚到百分之几
            "scroll_event_count": int(cs.draftScrollEventCount),             # 滚动次数
        }
    else:
        # ---- 前端没传行为数据 ----
        # ★ 全部填 0 而不是留空。这样导出的 CSV 每一行列数都一样，
        #   统计软件读进去不会因为缺列而报错。
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


# ── 第 10 块：接口入口（验身 + 加锁）★ ──────────────────────────────────────
@router.post("", response_model=ActionResponse)
async def submit_action(body: ActionIn, db: AsyncSession = Depends(db_session)) -> ActionResponse:
    """POST /api/action —— 提交一道题的作答。"""

    # ---- 先验明正身 ----
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
    # ────────────────────────────────────────────────────────────────────
    # ★ 大白话：这把锁挡的是一个真实发生过的线上事故。
    #
    # 事故经过：
    #   1. 医生点「提交」
    #   2. 手机网络卡住，请求半天没回来
    #   3. 前端等了 25 秒超时，显示「提交失败」
    #   4. 医生又点了一次
    #   5. 但第一个请求在服务器上**还在跑**
    #      —— 前端取消 fetch 只是不再等结果，并不能让后端停下来
    #   6. 于是两个一模一样的请求同时往数据库写
    #
    # 后果：actions 表对 case_presentation_id 有唯一约束（一道题只能有
    # 一个作答），后写的那个直接违反约束崩掉，返回 HTTP 500。
    # 医生看到的就是「网络异常，请稍后重试」——而他的答案其实早就存好了。
    #
    # 加锁之后：两个请求排队执行，第二个进来时会发现"这道题已经答过了"，
    # 走下面 _persist_action 的第 1 步，原样返回第一次的结果。
    # 医生完全无感，界面正常往下走。
    #
    # 锁是按 sessionId 加的，只挡同一个人自己的请求，不同医生之间零等待。
    # ────────────────────────────────────────────────────────────────────
    async with session_write_lock(db, session.id):
        return await _persist_action(db, session, case, body)


# ── 第 11 块：真正落库的五个步骤 ★ ──────────────────────────────────────────
async def _persist_action(
    db: AsyncSession, session: Session, case: Case, body: ActionIn
) -> ActionResponse:
    """★ 必须在 session_write_lock 里面调用，否则锁就白加了。"""

    # ---- 第 1 步：这道题是不是已经答过了？----
    existing_stmt = (
        select(CasePresentation)
        .where(
            CasePresentation.session_id == session.id,   # 是这个人的
            CasePresentation.case_id == case.id,         # 是这道题的
        )
        # 按开始时间排序，保证每次调用取到的顺序一致、结果可复现。
        .order_by(CasePresentation.started_at.asc())
        # selectinload 的意思是"顺便把关联的 action 也一起查出来"。
        # 不加的话，下面每访问一次 p.action 都会再查一次数据库
        #（这个问题叫 N+1 查询，是拖慢接口的典型原因）。
        .options(selectinload(CasePresentation.action))
    )
    existing_pres = (await db.execute(existing_stmt)).scalars().all()

    # 从查出来的记录里，找第一条"已经有作答"的。
    # next(生成器, 默认值) 的意思是"取第一个符合条件的，没有就返回默认值"。
    answered = next((p for p in existing_pres if p.action is not None), None)
    if answered is not None:
        # ★ 已经答过 → 原样返回第一次的结果，不覆盖、不新增。
        # 这就是「幂等」：重复提交无害。
        # 也是「流程只能向前」在服务端的保障——即使医生用浏览器后退键
        # 回到已答的题重新提交，服务器也只认第一次的答案。
        return ActionResponse(
            ok=True,
            casePresentationId=answered.id,
            # `or 0` 是防止 edit_distance 是 None（老数据可能没算过）。
            editDistance=answered.action.edit_distance or 0,
        )

    # ---- 第 2 步：找那条"已打开、还没作答"的记录 ----
    # 正常情况下 /api/case/open 已经建好了，这里直接复用它。
    in_progress_stmt = (
        select(CasePresentation)
        .outerjoin(Action, Action.case_presentation_id == CasePresentation.id)
        .where(
            CasePresentation.session_id == session.id,
            CasePresentation.case_id == case.id,
            Action.id.is_(None),   # 没挂 action = 还没作答
        )
        .order_by(CasePresentation.started_at.asc())
        .limit(1)
    )
    in_progress = (await db.execute(in_progress_stmt)).scalars().first()

    if in_progress is not None:
        # 找到了 → 把耗时信息补上去。
        presentation = in_progress
        presentation.order_index = body.orderIndex
        presentation.started_at = _to_dt(body.timing.startedAt)
        presentation.ended_at = _to_dt(body.timing.endedAt)
        presentation.duration_ms = body.timing.durationMs
        await db.flush()
    else:
        # 没找到 → 说明之前 /api/case/open 那次请求失败了（网络抖动）。
        # ★ 不能因此拒绝医生提交答案，直接补建一条记录。
        # 这就是为什么 /api/case/open 失败不影响答题。
        presentation = CasePresentation(
            session_id=session.id,
            case_id=case.id,
            order_index=body.orderIndex,
            started_at=_to_dt(body.timing.startedAt),
            ended_at=_to_dt(body.timing.endedAt),
            duration_ms=body.timing.durationMs,
        )
        db.add(presentation)
        # flush 是为了让数据库生成 presentation.id，
        # 因为下面两张表要用它当外键。
        await db.flush()

    # ---- 第 3 步：算编辑距离 ----
    # ★ 把 AI 的原始草稿和医生的最终定稿逐字符比对，得出"改了多少"。
    #   0     = 一个字都没改（完全照搬 AI）
    #   很小  = 只动了标点或个别词（走过场式的修改）
    #   很大  = 大幅重写（不信任 AI）
    # 这是衡量"过度信任 AI"的核心指标之一。
    edit_distance = levenshtein(case.ai_draft, body.finalReplyText)

    # 取个短名字，下面要用好几次。
    sa = body.selectedAction

    # 把行为数据翻译成问卷规定的 log_* 变量（第 9 块那个函数）。
    # exclude_none=True 表示"值是 None 的字段就不要了"，让存进去的数据干净些。
    incoming = body.clientStats.model_dump(exclude_none=True) if body.clientStats else None
    pdf_autolog = build_pdf_autolog_client_stats(body, incoming)

    # 把"为什么这么选"打包成一个小字典存进去，形如 {"code": "safety_risk"}。
    # 只有选「其他」时才多一个 "text" 键。
    reason_text = body.caseActionReasonText.strip() if body.caseActionReasonText else None
    reason_obj: dict[str, Any] = {"code": body.caseActionReasonCode.value}
    if reason_text:
        reason_obj["text"] = reason_text

    # ---- 第 4 步：写 actions 表（★ 医生的决定本身，研究的核心数据）----
    db.add(
        Action(
            case_presentation_id=presentation.id,
            selected_action=sa.value,   # .value 取枚举的字符串值，如 "send_as_is"

            # ↓ 这四个布尔字段是同一个信息的冗余存法。看着重复，
            #   但统计软件做回归时直接吃这种 0/1 列最方便。
            send_as_is_flag=sa == SelectedAction.send_as_is,
            edit_flag=sa == SelectedAction.edit_then_send,
            discard_flag=sa == SelectedAction.discard_and_rewrite,
            escalate_flag=sa == SelectedAction.escalate,

            # 上报子类型。没选上报就是 None。
            escalate_subtype=(body.escalateSubtype.value if body.escalateSubtype else None),

            # ★ 只有真的选了「上报」才存理由，否则存 None。
            # 防止这种情况：医生先选上报、写了理由、又改选别的处理方式，
            # 结果一条废弃的理由被留在数据库里，事后分析时造成误解。
            escalate_reason=(
                body.escalateReason.strip()
                if body.selectedAction == SelectedAction.escalate and body.escalateReason
                else None
            ),

            case_action_choice=_CHOICE_TO_PDF[sa],            # 问卷编号 1/2/3/4
            log_final_action=LOG_FINAL_ACTION_PDF[sa.value],  # 问卷规定的中文标签
            case_action_reason=reason_obj,                    # 为什么这么选

            final_reply_text=body.finalReplyText,             # 医生的定稿全文
            final_reply_char_count=len(body.finalReplyText),  # 字数
            edit_distance=edit_distance,                      # ★ 改了多少
            client_stats=pdf_autolog,                         # ★ 行为指标
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

    # ---- 一次性提交 ----
    # ★ 前面 flush 过的 presentation 改动，加上这两条新记录，在这一刻
    # 要么一起成功、要么一起失败。不会出现"有作答但没量表"的半截数据。
    await db.commit()

    return ActionResponse(
        ok=True,
        casePresentationId=presentation.id,
        editDistance=edit_distance,
    )
