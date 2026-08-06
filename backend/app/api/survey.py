"""
================================================================================
文件作用：前测问卷 + 后测问卷两个接口
================================================================================

医生的作答流程里有两份问卷，一头一尾：

  前测（做题之前）
      问的是背景信息：科室、职级、年资、每周处理多少患者消息、
      对 AI 起草有多熟悉。
      → 直接更新到 participants 表的独立列上。

  后测（做完 8 道题之后）
      40 多道 1~5 分量表 + 3 道开放题 + 手机尾号后 4 位。
      → 整包存成一个 JSON 放进 post_surveys 表，然后发放完成码。

★ 为什么前测存成列、后测存成 JSON？
  前测那 5 项是分析时最常用来分组的变量（"主治医师和住院医师的表现有差别
  吗"），做成独立列查起来方便。后测有 40 多道题，做成 40 多个列既难看又难
  改题，塞进一个 JSON 字段最省事，导出 CSV 时再摊平成一列一题。

★ 后测是整个流程的最后一步，也是发完成码的地方，所以专门做了防重复保护。

--------------------------------------------------------------------------------
本文件的代码块（从上到下）：
--------------------------------------------------------------------------------
  第 1 块  router                路由器（注意它没有前缀，两个接口各写各的网址）
  第 2 块  PreSurveyIn / PostSurveyIn   两个接口的输入格式
  第 3 块  _str() / _int()       两个小工具：安全地从字典里取值
  第 4 块  submit_pre_survey()   前测：更新被试档案
  第 5 块  submit_post_survey()  ★ 后测：校验 → 防重复写入 → 发完成码
================================================================================
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.db.base import utcnow
from app.db.locks import session_write_lock
from app.db.models import Participant, PostSurvey, Session, UiEvent
from app.schemas.post_survey_payload import PostSurveyV7Payload
from app.services.analysis import session_formal_performance


# ── 第 1 块：路由器 ──────────────────────────────────────────────────────────
# 这里没写 prefix=，因为两个接口的网址不共享前缀
#（一个是 /api/pre-survey，一个是 /api/post-survey），
# 所以在下面各自的装饰器里写完整路径。
router = APIRouter(tags=["survey"])


# ── 第 2 块：两个接口的输入格式 ─────────────────────────────────────────────
class PreSurveyIn(BaseModel):
    sessionId: str
    answers: dict  # 前端把所有前测答案打包成一个字典发上来


class PostSurveyIn(BaseModel):
    sessionId: str
    # 这里只声明"是个字典"，不逐题声明。
    # 真正的逐题校验交给 PostSurveyV7Payload（见第 5 块），
    # 这样校验规则集中在一个地方，加题只改那一个文件。
    payload: dict


# ── 第 3 块：两个取值小工具 ─────────────────────────────────────────────────
def _str(a: dict, key: str) -> str | None:
    """安全地从字典里取一个字符串。

    三种情况都当"没填"处理，返回 None：
        键不存在、值不是字符串（比如前端传了数字）、值是空白。

    ★ 为什么要这么小心：前测的校验没有后测那么严（只是 dict），
    所以脏数据有可能进来。宁可存 None，也不要把 "   " 或 123 存进
    "科室"这一列——那会让后面的分组统计出现莫名其妙的类别。
    """
    v = a.get(key)                                  # 取不到返回 None，不会报错
    if isinstance(v, str) and v.strip():            # 是字符串、且去掉空白后非空
        return v.strip()                            # 存去掉空白的版本
    return None


def _int(a: dict, key: str) -> int | None:
    """安全地取一个整数。不是整数就当没填。

    注意 Python 里 True 也算 int 的一种，理论上会漏过来。
    这里没管，因为前端的年资输入框只会传数字。
    """
    v = a.get(key)
    return v if isinstance(v, int) else None


# ── 第 4 块：前测问卷 ───────────────────────────────────────────────────────
@router.post("/api/pre-survey")
async def submit_pre_survey(
    body: PreSurveyIn, db: AsyncSession = Depends(db_session)
) -> dict:
    """POST /api/pre-survey —— 提交前测问卷。"""
    # 验明正身：会话和被试档案都得在。
    session = await db.get(Session, body.sessionId)
    if session is None:
        raise HTTPException(404, "Unknown session")
    participant = await db.get(Participant, session.participant_id)
    if participant is None:
        raise HTTPException(404, "Unknown participant")

    a = body.answers  # 取个短名字，下面要用好几次

    # ---- 把 5 项答案写到被试档案的列上 ----
    # ★ 这些字段名是 snake_case，而且和问卷 PDF 的编码表一一对应。
    #   前端传上来的键名必须完全一致（见 lib/forms/preSurveyConfig.ts 里的 id），
    #   改了名这里就取不到，那一列会静默地存成 None——不会报错，但数据没了。
    participant.pre_specialty = _str(a, "pre_specialty")                        # 科室
    participant.pre_training_level = _str(a, "pre_training_level")              # 职级
    participant.pre_years_post_residency = _int(a, "pre_years_post_residency")  # 规培后年资
    participant.pre_weekly_msg_volume = _str(a, "pre_weekly_msg_volume")        # 每周消息量
    participant.pre_ai_drafting_familiarity = _int(a, "pre_ai_drafting_familiarity")  # AI 熟悉度

    # ---- 同时把原始答案整包备份到埋点表 ----
    # 上面只挑了 5 个字段存成列。万一以后前测加题，或者要核对
    # "医生当时到底填了什么"，这里有一份完整的原始记录。
    db.add(
        UiEvent(
            session_id=session.id,
            event_type="pre_survey_submitted",
            payload=a,        # 整个字典原样存成 JSON
        )
    )

    # 写入数据库。participant 的字段修改和这条埋点一起提交。
    await db.commit()
    return {"ok": True}


# ── 第 5 块：后测问卷 ★ 流程的最后一步 ─────────────────────────────────────
@router.post("/api/post-survey")
async def submit_post_survey(
    body: PostSurveyIn, db: AsyncSession = Depends(db_session)
) -> dict:
    """POST /api/post-survey —— 提交后测问卷，返回完成码。"""
    session = await db.get(Session, body.sessionId)
    if session is None:
        raise HTTPException(404, "Unknown session")

    # ---- 步骤 1：严格校验整包答案 ----
    # PostSurveyV7Payload 会逐题检查（见 schemas/post_survey_payload.py）：
    #   40 多道量表必须都在 1~5 分之间
    #   ★ 注意力检查题必须答 4（筛掉一路点到底的敷衍作答）
    #   3 道开放题去掉空白后不能为空
    #   手机尾号必须正好 4 位数字
    #   不许有多余的字段
    # 任何一项不合规都在这里被拦下，脏数据进不了数据库。
    try:
        validated = PostSurveyV7Payload.model_validate(body.payload)
    except ValidationError as e:
        # Pydantic's e.errors() embeds the original exception object under
        # ctx["error"], which is NOT JSON-serializable. Passing it straight
        # into HTTPException(detail=...) makes the JSON response renderer
        # crash with a 500 instead of returning a clean 422. Flatten each
        # error into plain serializable fields.
        #
        # ★ 大白话（这是一个修过的真 bug）：
        # Pydantic 的报错对象里塞了一个 Python 异常实例，它不能转成 JSON。
        # 如果把它直接丢给 HTTPException，FastAPI 在把响应转成 JSON 时会
        # 自己崩掉，最后返回的是 500。
        # 后果：医生明明只是漏答了一道题，看到的却是"网络异常，请稍后重试"，
        # 他会以为是网络问题，反复重试反复失败，最后放弃——
        # 而正确的提示应该是"请检查您的答案"。
        # 所以这里手工把错误拍平成纯文本的 {字段, 说明}。
        safe_errors = [
            {
                # loc 是嵌套路径，比如 ("payload", "attn_post_1")，
                # 用 -> 连起来变成人能读的 "payload -> attn_post_1"。
                "field": " -> ".join(str(loc) for loc in err.get("loc", [])),
                "message": err.get("msg", ""),
            }
            for err in e.errors()
        ]
        # 422 = "你发来的数据不合规"，明确区别于 500（服务器自己坏了）。
        # 前端看到 422 会提示"请检查答案"，而不是"网络异常"。
        # `from e` 保留原始异常，服务器日志里能看到完整堆栈。
        raise HTTPException(status_code=422, detail=safe_errors) from e

    # ---- 步骤 2：算出完成码 ----
    # 规则：AIDR- 加上被试编号的末 8 位、转成大写。
    # 比如被试编号是 ...1a2b3c4d，完成码就是 AIDR-1A2B3C4D。
    #
    # ★ 注意它是"算"出来的，不是存下来的。同一个人算一百次结果都一样，
    #   所以重复提交也能拿到同一个码。
    # ★ 这一行故意放在锁外面：它不碰数据库，纯字符串运算。
    completion_code = f"AIDR-{session.participant_id[-8:].upper()}"

    # This is the last step of the study, so a stalled request the
    # participant retries would otherwise write a second post_survey row and
    # double-count them in every export. Serialize + skip on re-submit; the
    # first answers win and the retry still gets its completion code.
    #
    # ★ 大白话：为什么这里要加锁？
    #
    # 这是整个流程的最后一步，医生已经答了 20 分钟，最不能出错的就是这里。
    # 如果他因为卡顿重复点了提交，两个请求同时进来，就会写进两份后测问卷：
    #   - 导出数据时这个人被算成两个
    #   - "完成人数"统计虚高
    #   - 发报酬时对不上账
    #
    # 加锁 + 先查有没有，就能保证只写一份。
    # ★ 关键细节：即使跳过了写入，也**照样返回完成码**。
    #   医生看到的仍然是正常的完成页面，完全不知道后台跳过了一次写入。
    async with session_write_lock(db, session.id):
        # 查这个会话是不是已经交过后测了。
        # 只查 id 一列而不是整行，因为我们只关心"有没有"，查整行是浪费。
        already = (
            await db.execute(
                select(PostSurvey.id).where(PostSurvey.session_id == session.id).limit(1)
            )
        ).scalars().first()

        if already is None:
            # ---- 第一次提交：正常写入 ----
            db.add(
                PostSurvey(
                    participant_id=session.participant_id,
                    session_id=session.id,
                    # model_dump() 把校验后的对象转回普通字典，存成 JSON。
                    # 存的是校验后的版本（开放题已经 strip 过空白）。
                    payload=validated.model_dump(),
                )
            )
            now = utcnow()                    # 统一取一次时间，保证三处记录完全一致
            session.status = "completed"      # 会话状态：进行中 → 已完成
            session.ended_at = now

            participant = await db.get(Participant, session.participant_id)
            if participant is not None:
                # ★ 后台的"完成人数"统计看的就是这个字段。
                participant.completed_flag = True
                participant.completed_at = now
        # else 分支故意什么都不做：重复提交，保留第一次的答案。

        # ---- 步骤 3：算一下这个人答对了几道 ----
        # 拿 8 道正式题的作答去对照参考答案（练习题不算）。
        # 结果显示在完成页上给医生看。
        # ★ 放在锁里面，是为了让它读到的是刚写完的最新状态。
        performance = await session_formal_performance(db, session.id)

        # 提交。上面所有改动一起生效。
        # 提交的同时，Postgres 的事务级咨询锁自动释放。
        await db.commit()

    return {
        "ok": True,
        "completionCode": completion_code,   # 医生要抄下来领报酬的那串码
        "performance": performance,          # 答对几道的小结
    }
