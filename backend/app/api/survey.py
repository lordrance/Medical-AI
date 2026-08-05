"""前测问卷 + 后测问卷。

前测（答题前）：科室、职级、年资、每周消息量、对 AI 起草的熟悉度。
              直接更新到 participants 表的列上。
后测（答完 8 题后）：40 多道量表 + 3 道开放题 + 手机尾号。
              整包存成 JSON 放进 post_surveys 表，并发放完成码。

★ 后测是整个流程的最后一步，也是发完成码的地方，所以做了防重复保护。
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

router = APIRouter(tags=["survey"])


class PreSurveyIn(BaseModel):
    sessionId: str
    answers: dict  # 前端把所有前测答案打包成一个字典发上来


class PostSurveyIn(BaseModel):
    sessionId: str
    payload: dict  # 后测的整包答案，具体校验交给 PostSurveyV7Payload


def _str(a: dict, key: str) -> str | None:
    """安全地从字典里取字符串：不是字符串或者是空白，一律当没填（返回 None）。

    这样即使前端传了脏数据（数字、null、纯空格），也不会写进数据库。
    """
    v = a.get(key)
    if isinstance(v, str) and v.strip():
        return v.strip()
    return None


def _int(a: dict, key: str) -> int | None:
    """安全地取整数：不是整数就当没填。"""
    v = a.get(key)
    return v if isinstance(v, int) else None


@router.post("/api/pre-survey")
async def submit_pre_survey(
    body: PreSurveyIn, db: AsyncSession = Depends(db_session)
) -> dict:
    """POST /api/pre-survey —— 提交前测问卷。"""
    session = await db.get(Session, body.sessionId)
    if session is None:
        raise HTTPException(404, "Unknown session")
    participant = await db.get(Participant, session.participant_id)
    if participant is None:
        raise HTTPException(404, "Unknown participant")

    a = body.answers

    # 前测答案直接更新到被试档案的列上（不像后测那样存 JSON），
    # 因为这几项是分析时最常用来分组的变量，做成独立列查询更方便。
    # 字段名用 snake_case 且与问卷 PDF 的编码表一致，不要改名。
    participant.pre_specialty = _str(a, "pre_specialty")                    # 科室
    participant.pre_training_level = _str(a, "pre_training_level")          # 职级
    participant.pre_years_post_residency = _int(a, "pre_years_post_residency")  # 规培后年资
    participant.pre_weekly_msg_volume = _str(a, "pre_weekly_msg_volume")    # 每周处理多少条患者消息
    participant.pre_ai_drafting_familiarity = _int(a, "pre_ai_drafting_familiarity")  # 对 AI 起草的熟悉度

    # 同时把原始答案整包存一份到埋点表。上面的列只存了 5 个字段，
    # 万一以后前测加题、或者要核对原始作答，这里有完整备份。
    db.add(
        UiEvent(
            session_id=session.id,
            event_type="pre_survey_submitted",
            payload=a,
        )
    )
    await db.commit()
    return {"ok": True}


@router.post("/api/post-survey")
async def submit_post_survey(
    body: PostSurveyIn, db: AsyncSession = Depends(db_session)
) -> dict:
    """POST /api/post-survey —— 提交后测问卷，返回完成码。"""
    session = await db.get(Session, body.sessionId)
    if session is None:
        raise HTTPException(404, "Unknown session")

    # 严格校验整包答案：40 多道量表必须都在 1~5，注意力检查题必须答 4，
    # 3 道开放题不能空，手机尾号必须是 4 位数字。
    # 任何一项不合规都返回 422，前端会提示「请检查答案」而不是「网络错误」。
    try:
        validated = PostSurveyV7Payload.model_validate(body.payload)
    except ValidationError as e:
        # Pydantic's e.errors() embeds the original exception object under
        # ctx["error"], which is NOT JSON-serializable. Passing it straight
        # into HTTPException(detail=...) makes the JSON response renderer
        # crash with a 500 instead of returning a clean 422. Flatten each
        # error into plain serializable fields.
        #
        # 中文：Pydantic 报错对象里塞了一个 Python 异常实例，它不能转成 JSON。
        # 直接把它丢给 HTTPException，FastAPI 渲染响应时会自己崩掉，
        # 结果医生看到的是 500「网络异常」而不是「有题目没答对」。
        # 所以这里手工拍平成纯文本的 {字段, 说明}。
        safe_errors = [
            {
                "field": " -> ".join(str(loc) for loc in err.get("loc", [])),
                "message": err.get("msg", ""),
            }
            for err in e.errors()
        ]
        raise HTTPException(status_code=422, detail=safe_errors) from e

    # 完成码 = AIDR- + 被试 ID 的末 8 位（大写）。
    # 医生把这串码报给招募方来领报酬。同一个人每次算出来都一样。
    completion_code = f"AIDR-{session.participant_id[-8:].upper()}"

    # This is the last step of the study, so a stalled request the
    # participant retries would otherwise write a second post_survey row and
    # double-count them in every export. Serialize + skip on re-submit; the
    # first answers win and the retry still gets its completion code.
    #
    # 中文：这是流程的最后一步。如果医生因为卡顿重复点了提交，
    # 就会写进两份后测问卷，导出数据时这个人被算成两个，完成人数也会虚高。
    # 加锁 + 先查有没有：已经有了就跳过写入，但**照样返回完成码**，
    # 医生看到的仍然是正常的完成页面，不会以为自己失败了。
    async with session_write_lock(db, session.id):
        already = (
            await db.execute(
                select(PostSurvey.id).where(PostSurvey.session_id == session.id).limit(1)
            )
        ).scalars().first()

        if already is None:
            # 第一次提交：存答案 + 标记这个人已完成。
            db.add(
                PostSurvey(
                    participant_id=session.participant_id,
                    session_id=session.id,
                    payload=validated.model_dump(),  # 整包 JSON
                )
            )
            now = utcnow()
            session.status = "completed"
            session.ended_at = now

            participant = await db.get(Participant, session.participant_id)
            if participant is not None:
                participant.completed_flag = True   # 后台统计「完成人数」看这个字段
                participant.completed_at = now

        # 顺手算一下这个人 8 道正式题答对了几道（对照预设的参考答案），
        # 在完成页上展示给医生看。练习题不计入。
        performance = await session_formal_performance(db, session.id)
        await db.commit()

    return {
        "ok": True,
        "completionCode": completion_code,
        "performance": performance,
    }
