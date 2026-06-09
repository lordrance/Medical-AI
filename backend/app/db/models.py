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
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Content tables
# ---------------------------------------------------------------------------


class Case(Base):
    """A single experiment case (practice or formal)."""

    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    is_practice: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    defect_present: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    defect_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)

    patient_message: Mapped[str] = mapped_column(Text, nullable=False)
    chart_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    ai_draft: Mapped[str] = mapped_column(Text, nullable=False)
    facts_used: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    risk_cue: Mapped[str] = mapped_column(Text, nullable=False, default="")
    checklist: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    gold_action: Mapped[str] = mapped_column(String(32), nullable=False)
    gold_action_alternates: Mapped[list[str]] = mapped_column(JSON, default=list)

    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="zh-CN", nullable=False)

    presentations: Mapped[list["CasePresentation"]] = relationship(
        back_populates="case",
    )


class OrderTemplate(Base):
    __tablename__ = "order_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order: Mapped[list[str]] = mapped_column(JSON, nullable=False)

    participants: Mapped[list["Participant"]] = relationship(
        back_populates="order_template",
    )


# ---------------------------------------------------------------------------
# Participant tables
# ---------------------------------------------------------------------------


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    condition: Mapped[str] = mapped_column(String(32), nullable=False)
    order_template_id: Mapped[int] = mapped_column(
        ForeignKey("order_templates.id"), nullable=False
    )

    pre_specialty: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pre_training_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pre_years_post_residency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pre_weekly_msg_volume: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pre_ai_drafting_familiarity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_flag: Mapped[bool] = mapped_column(Boolean, default=False)

    order_template: Mapped[OrderTemplate] = relationship(back_populates="participants")
    sessions: Mapped[list["Session"]] = relationship(back_populates="participant")
    post_surveys: Mapped[list["PostSurvey"]] = relationship(back_populates="participant")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id"), nullable=False
    )
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
    __tablename__ = "case_presentations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

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
    __tablename__ = "actions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    case_presentation_id: Mapped[str] = mapped_column(
        ForeignKey("case_presentations.id"), unique=True, nullable=False
    )

    selected_action: Mapped[str] = mapped_column(String(32), nullable=False)
    send_as_is_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    edit_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    discard_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    escalate_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    escalate_subtype: Mapped[str | None] = mapped_column(String(64), nullable=True)
    escalate_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    case_action_choice: Mapped[int] = mapped_column(Integer, nullable=False)
    log_final_action: Mapped[str] = mapped_column(String(32), nullable=False)
    case_action_reason: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    final_reply_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    final_reply_char_count: Mapped[int] = mapped_column(Integer, default=0)
    edit_distance: Mapped[int | None] = mapped_column(Integer, nullable=True)

    client_stats: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    server_received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    presentation: Mapped[CasePresentation] = relationship(back_populates="action")


class CaseSurvey(Base):
    __tablename__ = "case_surveys"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    case_presentation_id: Mapped[str] = mapped_column(
        ForeignKey("case_presentations.id"), unique=True, nullable=False
    )

    case_decision_confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    case_draft_helpfulness: Mapped[int] = mapped_column(Integer, nullable=False)

    server_received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    presentation: Mapped[CasePresentation] = relationship(back_populates="case_survey")


class PostSurvey(Base):
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
    __tablename__ = "ui_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    case_presentation_id: Mapped[str | None] = mapped_column(
        ForeignKey("case_presentations.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
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
