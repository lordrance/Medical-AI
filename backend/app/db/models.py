"""★ 数据库的全部表结构定义（11 张表）。

这个文件是「数据长什么样」的唯一真相来源。SQLAlchemy 会根据这里的类
自动生成 SQL。要改表结构必须同时写一个 alembic 迁移脚本，否则生产库不会变。

表分三类：

  内容表（题目本身，启动时灌进去，运行中不变）
    cases            9 道题的全部内容
    order_templates  4 套题目顺序

  被试数据表（医生答题产生的，这是研究的成果）
    participants        一个医生一行
    sessions            一次作答会话
    case_presentations  「某人看了某题」
    actions             医生对这题的处理决定  ← 核心
    case_surveys        答完这题的两道小量表
    post_surveys        后测问卷整包
    ui_events           行为埋点
    voice_recordings    语音录音（V4 已停用）

  运维表
    llm_calls / cohort_summaries  记录调用 AI 写研究总结的账

命名约定（不要改）：问卷相关字段用 snake_case 且与问卷 PDF 编码表一致，
例如 pre_specialty、log_final_action；而元数据字段（sessionId 等）在
前端 API 里用 camelCase。这个分裂是故意的，对应已发表的研究工具。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow


def _uuid() -> str:
    """生成一个 32 位十六进制的随机 ID。

    用 UUID 而不是自增数字，是因为这些 ID 会出现在网址和前端里，
    自增 ID 会泄露「我是第几个被试」，也方便别人猜到别人的 ID。
    """
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Content tables  —— 题目内容表：启动时由 seed 脚本灌入，运行中只读
# ---------------------------------------------------------------------------


class Case(Base):
    """A single experiment case (practice or formal).

    中文：一道题。共 9 行 = 1 道练习 + 8 道正式。
    内容来自 backend/data/cases.json，改题目改那个文件然后重新 seed。
    """

    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 如 "case_01" "case_practice"
    is_practice: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)  # 高风险 / 低风险

    # --- 实验设计字段（★ 绝不能发给前端，否则被试能看到答案）---
    defect_present: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 这道题的 AI 草稿里故意埋了什么错（8 道正式题里 7 道有错、1 道没错）
    defect_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)  # 这题想测什么

    # --- 医生会看到的内容 ---
    patient_message: Mapped[str] = mapped_column(Text, nullable=False)   # 患者发来的消息
    chart_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)  # 病历摘要
    ai_draft: Mapped[str] = mapped_column(Text, nullable=False)          # ★ AI 起草的回复（写死）

    # --- V3 的「风险提示面板」数据。V4 不显示，但仍导出作为研究元数据 ---
    facts_used: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    risk_cue: Mapped[str] = mapped_column(Text, nullable=False, default="")
    checklist: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    # --- 参考答案（判分用）---
    # gold_action：研究团队认为最恰当的处理方式
    # gold_action_alternates：次优但也可接受的处理方式，判分时也算对
    gold_action: Mapped[str] = mapped_column(String(32), nullable=False)
    gold_action_alternates: Mapped[list[str]] = mapped_column(JSON, default=list)

    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="zh-CN", nullable=False)

    # relationship 不是数据库里的真实列，是 SQLAlchemy 提供的便捷访问：
    # 写 case.presentations 就能拿到所有看过这题的记录。
    presentations: Mapped[list["CasePresentation"]] = relationship(
        back_populates="case",
    )


class OrderTemplate(Base):
    """题目顺序模板。共 4 行。

    每个被试随机抽一套。这样避免「所有人都先做第 1 题」造成的顺序效应
    （越到后面越疲劳、越熟练，会污染结果）。
    约束：唯一那道「AI 草稿没错」的题必须排在前半段（由 validate_data.py 检查）。
    """

    __tablename__ = "order_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # 1~4
    order: Mapped[list[str]] = mapped_column(JSON, nullable=False)  # 8 个 case_id 的数组

    # 反向关联：写 template.participants 就能拿到抽中这套顺序的所有被试。
    # 和 Participant.order_template 是一对，两边必须都在，缺一个 SQLAlchemy 启动就报错。
    participants: Mapped[list["Participant"]] = relationship(
        back_populates="order_template",
    )


# ---------------------------------------------------------------------------
# Participant tables —— 被试数据表：这些才是研究的成果
# ---------------------------------------------------------------------------


class Participant(Base):
    """一个医生 = 一行。生产库现在有 117 行。

    ★ 完全匿名：没有姓名、手机号、医院。只有一个随机 ID 和几项人口学变量。
    （后测里的手机尾号 4 位存在 post_surveys 的 JSON 里，仅用于发报酬对账。）
    """

    __tablename__ = "participants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    condition: Mapped[str] = mapped_column(String(32), nullable=False)  # V4 恒为 "single"
    order_template_id: Mapped[int] = mapped_column(
        ForeignKey("order_templates.id"), nullable=False  # 抽到的是哪套题目顺序
    )

    # --- 前测问卷的答案。可空是因为建档时还没填，提交前测后才写入 ---
    pre_specialty: Mapped[str | None] = mapped_column(String(64), nullable=True)          # 科室
    pre_training_level: Mapped[str | None] = mapped_column(String(64), nullable=True)     # 职级
    pre_years_post_residency: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 规培后年资
    pre_weekly_msg_volume: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 每周消息量
    pre_ai_drafting_familiarity: Mapped[int | None] = mapped_column(Integer, nullable=True)  # AI 熟悉度

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # ★ 提交后测问卷时才置为 True。后台「完成人数」统计的就是这个字段。
    completed_flag: Mapped[bool] = mapped_column(Boolean, default=False)

    order_template: Mapped[OrderTemplate] = relationship(back_populates="participants")
    sessions: Mapped[list["Session"]] = relationship(back_populates="participant")
    post_surveys: Mapped[list["PostSurvey"]] = relationship(back_populates="participant")


class Session(Base):
    """一次作答会话。理论上一个人可以有多次，实际用下来是一对一（117 : 117）。

    sessionId 是前端最重要的凭证：存在浏览器里，之后每个请求都要带上它，
    服务器靠它认人。它本身就是身份，所以是随机 UUID、不可猜。
    """

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id"), nullable=False
    )
    # "active"（进行中）→ "completed"（提交后测后）
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    participant: Mapped[Participant] = relationship(back_populates="sessions")
    presentations: Mapped[list["CasePresentation"]] = relationship(
        back_populates="session"
    )
    ui_events: Mapped[list["UiEvent"]] = relationship(back_populates="session")
    post_surveys: Mapped[list["PostSurvey"]] = relationship(back_populates="session")


class CasePresentation(Base):
    """「某人看了某道题」。每人 9 行（1 练习 + 8 正式），生产库共 350 行。

    它是连接「人」和「题」的中间表，也是 actions / case_surveys / ui_events
    共同挂靠的锚点——这样才知道某个点击行为发生在谁的哪道题上。

    ★ 注意：这张表**没有** (session_id, case_id) 唯一约束。历史上因此产生过
    23 组重复行，现在靠 session_write_lock 在应用层杜绝（见 db/locks.py）。
    """

    __tablename__ = "case_presentations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 第几题，-1 = 练习

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session: Mapped[Session] = relationship(back_populates="presentations")
    case: Mapped[Case] = relationship(back_populates="presentations")
    action: Mapped["Action | None"] = relationship(
        back_populates="presentation", uselist=False
    )
    case_survey: Mapped["CaseSurvey | None"] = relationship(
        back_populates="presentation", uselist=False
    )
    ui_events: Mapped[list["UiEvent"]] = relationship(back_populates="presentation")

    __table_args__ = (
        Index("ix_case_presentations_session_order", "session_id", "order_index"),
    )


class Action(Base):
    """★ 研究的核心数据：医生对这道题做了什么决定。生产库共 296 行。

    一条 case_presentation 最多对应一条 action（下面的 unique=True 保证）。
    这个唯一约束正是「重复提交会返回 500」那个 bug 的直接原因——
    现在由 session_write_lock 在写入前就把并发挡掉了。
    """

    __tablename__ = "actions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    case_presentation_id: Mapped[str] = mapped_column(
        # ★ unique=True：一道题只能有一个作答。数据库层面的最后防线。
        ForeignKey("case_presentations.id"), unique=True, nullable=False
    )

    # 四选一的处理方式：send_as_is / edit_then_send / discard_and_rewrite / escalate
    selected_action: Mapped[str] = mapped_column(String(32), nullable=False)

    # 下面四个 0/1 列是 selected_action 的冗余展开。看着重复，但 SPSS / R
    # 做回归时直接吃这种哑变量最省事，不用再手工转换。
    send_as_is_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    edit_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    discard_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    escalate_flag: Mapped[bool] = mapped_column(Boolean, default=False)

    # 只有选「上报」时才有值
    escalate_subtype: Mapped[str | None] = mapped_column(String(64), nullable=True)
    escalate_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 问卷 PDF 规定的编码：数字版 1/2/3/4 和文字版标签，导出后直接对应编码表
    case_action_choice: Mapped[int] = mapped_column(Integer, nullable=False)
    log_final_action: Mapped[str] = mapped_column(String(32), nullable=False)
    # 为什么这么选：{"code": "safety_risk"}，选「其他」时多一个 "text" 键
    case_action_reason: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    final_reply_text: Mapped[str] = mapped_column(Text, nullable=False, default="")  # 医生的定稿全文
    final_reply_char_count: Mapped[int] = mapped_column(Integer, default=0)
    # ★ 编辑距离：医生把 AI 草稿改了多少个字符。0 = 一字未改。
    # 这是衡量「过度信任 AI」的关键指标。
    edit_distance: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 行为指标整包（log_case_review_time、log_verification_clicks 等）
    client_stats: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    server_received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    presentation: Mapped[CasePresentation] = relationship(back_populates="action")


class CaseSurvey(Base):
    """答完每道题后紧跟的两道小量表（1~5 分）。生产库共 296 行。

    和 actions 一样，一道题只能有一条（unique=True）。
    """

    __tablename__ = "case_surveys"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    case_presentation_id: Mapped[str] = mapped_column(
        ForeignKey("case_presentations.id"), unique=True, nullable=False
    )

    case_decision_confidence: Mapped[int] = mapped_column(Integer, nullable=False)  # 我对刚才的判断有信心
    case_draft_helpfulness: Mapped[int] = mapped_column(Integer, nullable=False)    # AI 草稿在本案例中有帮助

    server_received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    presentation: Mapped[CasePresentation] = relationship(back_populates="case_survey")


class PostSurvey(Base):
    """后测问卷。一个人一份，生产库现在 16 份（= 16 个人完整做完了）。

    40 多道量表 + 3 道开放题 + 手机尾号全部塞在 payload 这一个 JSON 列里，
    而不是拆成 40 多个数据库列。这样问卷改题不用改表结构，
    校验交给 schemas/post_survey_payload.py 那个 Pydantic 模型。
    导出 CSV 时再把 JSON 摊平成一列一题。

    ★ 这张表没有 session_id 唯一约束，防重复靠 survey.py 里的
    session_write_lock + 先查后写。
    """

    __tablename__ = "post_surveys"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    server_received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    participant: Mapped[Participant] = relationship(back_populates="post_surveys")
    session: Mapped[Session] = relationship(back_populates="post_surveys")


class UiEvent(Base):
    """行为埋点。生产库共 2387 条，是「医生是怎么看的」的原始素材。

    典型事件：case_view_start（开始看这题）、chart_expanded（展开病历）、
    page_blur（切到别的 App）、action_button_selected（选了某个处理方式）。
    """

    __tablename__ = "ui_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    # 可空：前测/后测问卷阶段的事件不属于任何一道题
    case_presentation_id: Mapped[str | None] = mapped_column(
        ForeignKey("case_presentations.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # 两个时间戳都记：浏览器的可能不准（用户改了系统时间、时区不对），
    # 服务器的绝对可信。分析时序用服务器时间，算「用户感知的间隔」用浏览器时间。
    client_ts: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    server_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    session: Mapped[Session] = relationship(back_populates="ui_events")
    presentation: Mapped[CasePresentation | None] = relationship(
        back_populates="ui_events"
    )

    # 索引 = 给数据库建的「目录」，让按这些字段查询时不用逐行扫描。
    # 这张表行数最多，后台看板要按 session + 事件类型聚合，没索引会很慢。
    __table_args__ = (
        Index("ix_ui_events_session_type", "session_id", "event_type"),
        Index("ix_ui_events_presentation", "case_presentation_id"),
    )


# ---------------------------------------------------------------------------
# Voice recordings (V4: open-ended post-survey items L1/L2/L3 may attach
# audio captured via MediaRecorder for offline human transcription)
# ---------------------------------------------------------------------------


class VoiceRecording(Base):
    __tablename__ = "voice_recordings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id"), nullable=False
    )
    # Which post-survey item the recording is for, e.g.
    # "post_qual_l1_ehr_pain_ai_substitution". Free-form string; not a FK.
    question_id: Mapped[str] = mapped_column(String(128), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_voice_recordings_session", "session_id"),
        Index("ix_voice_recordings_session_question", "session_id", "question_id"),
    )


# ---------------------------------------------------------------------------
# LLM tables
# ---------------------------------------------------------------------------


class LLMCall(Base):
    """Audit log for every LLM invocation."""

    __tablename__ = "llm_calls"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class CohortSummary(Base):
    """A cohort-level natural language summary generated by an admin."""

    __tablename__ = "cohort_summaries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
