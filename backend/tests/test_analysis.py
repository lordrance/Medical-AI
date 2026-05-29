"""Unit tests for app/services/analysis.py.

Closes the QA gap (26% coverage). Each test directly seeds rows into the DB
using the SQLAlchemy models — bypassing the API — so each scenario stays
small and the aggregation function is exercised against precise inputs.

Conftest's autouse fixture drops + recreates schema between tests, so we
start each test with an empty database.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Action,
    Case,
    CasePresentation,
    LLMCall,
    OrderTemplate,
    Participant,
    Session as SessionModel,
    UiEvent,
)
from app.db.session import get_session_factory
from app.services.analysis import (
    _percentile,
    active_sessions,
    completion_stats,
    completion_timeseries,
    confusion_matrix,
    llm_call_stats,
    log_stats_by_condition,
    per_case_stats,
    per_participant_stats,
    session_formal_performance,
    ui_event_frequency,
)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    factory = get_session_factory()
    async with factory() as s:
        yield s


def _uid() -> str:
    return uuid.uuid4().hex


async def _mk_order_template(db: AsyncSession, tpl_id: int = 1) -> OrderTemplate:
    tpl = OrderTemplate(id=tpl_id, order=[])
    db.add(tpl)
    await db.flush()
    return tpl


async def _mk_case(
    db: AsyncSession,
    *,
    case_id: str,
    gold: str,
    alternates: list[str] | None = None,
    defect_present: bool = False,
    is_practice: bool = False,
    risk_level: str = "medium",
) -> Case:
    c = Case(
        id=case_id,
        is_practice=is_practice,
        risk_level=risk_level,
        defect_present=defect_present,
        defect_type=None,
        purpose=None,
        patient_message="msg",
        chart_snapshot={},
        ai_draft="draft",
        facts_used=[],
        risk_cue="",
        checklist=[],
        gold_action=gold,
        gold_action_alternates=alternates or [],
    )
    db.add(c)
    await db.flush()
    return c


async def _mk_participant(
    db: AsyncSession,
    *,
    condition: str = "plain",
    completed: bool = False,
    template_id: int = 1,
) -> Participant:
    p = Participant(
        id=_uid(),
        condition=condition,
        order_template_id=template_id,
        completed_flag=completed,
    )
    db.add(p)
    await db.flush()
    return p


async def _mk_session(db: AsyncSession, *, participant_id: str) -> SessionModel:
    s = SessionModel(id=_uid(), participant_id=participant_id, status="active")
    db.add(s)
    await db.flush()
    return s


async def _mk_submission(
    db: AsyncSession,
    *,
    session_id: str,
    case_id: str,
    selected: str,
    order_index: int = 0,
    duration_ms: int | None = 5000,
    edit_distance: int | None = 0,
    server_received_at: datetime | None = None,
    escalate_flag: bool | None = None,
    send_as_is_flag: bool | None = None,
) -> tuple[CasePresentation, Action]:
    """Create a (presentation, action) pair. `flags` default to consistency with `selected`."""
    pres = CasePresentation(
        id=_uid(),
        session_id=session_id,
        case_id=case_id,
        order_index=order_index,
        duration_ms=duration_ms,
    )
    db.add(pres)
    await db.flush()

    if send_as_is_flag is None:
        send_as_is_flag = selected == "send_as_is"
    if escalate_flag is None:
        escalate_flag = selected == "escalate"

    choice_map = {
        "send_as_is": 1,
        "edit_then_send": 2,
        "discard_and_rewrite": 3,
        "escalate": 4,
    }
    log_final_map = {
        "send_as_is": "直接发送",
        "edit_then_send": "编辑后发送",
        "discard_and_rewrite": "弃用并重写",
        "escalate": "升级处理",
    }
    a = Action(
        id=_uid(),
        case_presentation_id=pres.id,
        selected_action=selected,
        send_as_is_flag=send_as_is_flag,
        edit_flag=selected == "edit_then_send",
        discard_flag=selected == "discard_and_rewrite",
        escalate_flag=escalate_flag,
        escalate_subtype="urgent_evaluation" if escalate_flag else None,
        escalate_reason="reason" if escalate_flag else None,
        case_action_choice=choice_map.get(selected, 1),
        log_final_action=log_final_map.get(selected, "直接发送"),
        case_action_reason={"code": "basically_ok"},
        final_reply_text="reply",
        final_reply_char_count=5,
        edit_distance=edit_distance,
        client_stats={},
    )
    if server_received_at is not None:
        a.server_received_at = server_received_at
    db.add(a)
    await db.flush()
    return pres, a


# ---------------------------------------------------------------------------
# completion_stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_completion_stats_empty_db(db: AsyncSession) -> None:
    """Zero participants must not divide by zero."""
    result = await completion_stats(db)
    assert result == {
        "totalParticipants": 0,
        "completed": 0,
        "completionRate": 0.0,
        "byCondition": [],
    }


@pytest.mark.asyncio
async def test_completion_stats_single_participant_not_completed(db: AsyncSession) -> None:
    await _mk_order_template(db)
    await _mk_participant(db, condition="plain", completed=False)
    await db.commit()
    result = await completion_stats(db)
    assert result["totalParticipants"] == 1
    assert result["completed"] == 0
    assert result["completionRate"] == 0.0
    assert {"condition": "plain", "count": 1} in result["byCondition"]


@pytest.mark.asyncio
async def test_completion_stats_mixed_conditions(db: AsyncSession) -> None:
    await _mk_order_template(db)
    await _mk_participant(db, condition="plain", completed=True)
    await _mk_participant(db, condition="plain", completed=False)
    await _mk_participant(db, condition="guardrail", completed=True)
    await _mk_participant(db, condition="guardrail", completed=True)
    await db.commit()
    result = await completion_stats(db)
    assert result["totalParticipants"] == 4
    assert result["completed"] == 3
    assert result["completionRate"] == 0.75
    by_cond = {row["condition"]: row["count"] for row in result["byCondition"]}
    assert by_cond == {"plain": 2, "guardrail": 2}


# ---------------------------------------------------------------------------
# confusion_matrix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confusion_matrix_empty_db(db: AsyncSession) -> None:
    """No data must not raise and must return a well-formed empty matrix."""
    result = await confusion_matrix(db)
    assert result["actions"] == [
        "send_as_is",
        "edit_then_send",
        "discard_and_rewrite",
        "escalate",
    ]
    assert result["actionsZh"] == ["原样发送", "编辑后发送", "弃用并重写", "升级处理"]
    assert result["matrix"] == [[0] * 4 for _ in range(4)]
    assert result["total"] == 0
    assert result["accuracy"] == 0.0  # not NaN, not crashed


@pytest.mark.asyncio
async def test_confusion_matrix_all_escalate_gold(db: AsyncSession) -> None:
    """Degenerate gold distribution: only the last row of the matrix is populated."""
    await _mk_order_template(db)
    for i in range(3):
        await _mk_case(db, case_id=f"e_{i}", gold="escalate", defect_present=True)
    pt = await _mk_participant(db)
    sess = await _mk_session(db, participant_id=pt.id)
    # 2 correct, 1 wrong
    await _mk_submission(db, session_id=sess.id, case_id="e_0", selected="escalate")
    await _mk_submission(db, session_id=sess.id, case_id="e_1", selected="escalate")
    await _mk_submission(db, session_id=sess.id, case_id="e_2", selected="send_as_is")
    await db.commit()

    result = await confusion_matrix(db)
    assert result["total"] == 3
    # Row 3 (escalate) is the only one with non-zero counts
    assert result["matrix"][0] == [0, 0, 0, 0]
    assert result["matrix"][1] == [0, 0, 0, 0]
    assert result["matrix"][2] == [0, 0, 0, 0]
    assert result["matrix"][3] == [1, 0, 0, 2]  # 1 send_as_is, 2 escalate
    assert result["accuracy"] == pytest.approx(2 / 3)


@pytest.mark.asyncio
async def test_confusion_matrix_tied_off_diagonal(db: AsyncSession) -> None:
    """Everyone picks send_as_is regardless of gold: matrix column-0 dominated."""
    await _mk_order_template(db)
    await _mk_case(db, case_id="c_send", gold="send_as_is")
    await _mk_case(db, case_id="c_edit", gold="edit_then_send", defect_present=True)
    await _mk_case(db, case_id="c_esc", gold="escalate", defect_present=True)
    pt = await _mk_participant(db)
    sess = await _mk_session(db, participant_id=pt.id)
    for cid in ("c_send", "c_edit", "c_esc"):
        await _mk_submission(db, session_id=sess.id, case_id=cid, selected="send_as_is")
    await db.commit()

    result = await confusion_matrix(db)
    assert result["total"] == 3
    # Column 0 has 1 in each populated gold row
    assert result["matrix"][0][0] == 1  # gold=send, sel=send  → correct
    assert result["matrix"][1][0] == 1  # gold=edit, sel=send
    assert result["matrix"][3][0] == 1  # gold=escalate, sel=send
    assert result["accuracy"] == pytest.approx(1 / 3)


@pytest.mark.asyncio
async def test_confusion_matrix_excludes_practice(db: AsyncSession) -> None:
    """Practice case submissions must not enter the formal-case matrix."""
    await _mk_order_template(db)
    await _mk_case(db, case_id="practice", gold="send_as_is", is_practice=True)
    pt = await _mk_participant(db)
    sess = await _mk_session(db, participant_id=pt.id)
    await _mk_submission(db, session_id=sess.id, case_id="practice", selected="send_as_is")
    await db.commit()

    result = await confusion_matrix(db)
    assert result["total"] == 0
    assert result["matrix"] == [[0] * 4 for _ in range(4)]


@pytest.mark.asyncio
async def test_confusion_matrix_dedup_keeps_latest_submission(db: AsyncSession) -> None:
    """If the same (session, case) is submitted twice, only the latest counts."""
    await _mk_order_template(db)
    await _mk_case(db, case_id="c", gold="escalate", defect_present=True)
    pt = await _mk_participant(db)
    sess = await _mk_session(db, participant_id=pt.id)

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # First (earlier) submission: wrong
    await _mk_submission(
        db,
        session_id=sess.id,
        case_id="c",
        selected="send_as_is",
        server_received_at=base,
    )
    # Second (later) submission: correct — should win
    await _mk_submission(
        db,
        session_id=sess.id,
        case_id="c",
        selected="escalate",
        server_received_at=base + timedelta(minutes=10),
    )
    await db.commit()

    result = await confusion_matrix(db)
    assert result["total"] == 1
    # gold=escalate, sel=escalate → matrix[3][3]
    assert result["matrix"][3][3] == 1
    assert result["matrix"][3][0] == 0
    assert result["accuracy"] == 1.0


@pytest.mark.asyncio
async def test_confusion_matrix_uses_gold_alternates_for_accuracy(db: AsyncSession) -> None:
    """A selection in goldActionAlternates counts as accurate, but populates the
    off-diagonal of the matrix (matrix counts raw selection, not match status)."""
    await _mk_order_template(db)
    await _mk_case(
        db, case_id="c", gold="edit_then_send", alternates=["discard_and_rewrite"]
    )
    pt = await _mk_participant(db)
    sess = await _mk_session(db, participant_id=pt.id)
    await _mk_submission(
        db, session_id=sess.id, case_id="c", selected="discard_and_rewrite"
    )
    await db.commit()

    result = await confusion_matrix(db)
    assert result["total"] == 1
    assert result["matrix"][1][2] == 1  # gold=edit, sel=discard
    assert result["accuracy"] == 1.0  # but accuracy honors alternates


# ---------------------------------------------------------------------------
# per_case_stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_per_case_stats_empty(db: AsyncSession) -> None:
    result = await per_case_stats(db)
    assert result == []


@pytest.mark.asyncio
async def test_per_case_stats_full_aggregation(db: AsyncSession) -> None:
    """Cover match_gold / match_alt / unsafe_send / error_survival /
    appropriate_escalation / mean_duration / mean_edit_distance in one scenario."""
    await _mk_order_template(db)
    # case_a: gold=escalate (defect_present=True) — for error_survival + appropriate_escalation
    await _mk_case(
        db, case_id="case_a", gold="escalate", defect_present=True, risk_level="high"
    )
    # case_b: gold=send_as_is (non-defect) — for unsafe_send (none since not defect)
    await _mk_case(db, case_id="case_b", gold="send_as_is", defect_present=False)

    pt1 = await _mk_participant(db, condition="plain")
    pt2 = await _mk_participant(db, condition="guardrail")
    s1 = await _mk_session(db, participant_id=pt1.id)
    s2 = await _mk_session(db, participant_id=pt2.id)

    # case_a: 1 correct escalate, 1 wrong send_as_is (= error_survival + unsafe_send)
    await _mk_submission(
        db,
        session_id=s1.id,
        case_id="case_a",
        selected="escalate",
        duration_ms=4000,
        edit_distance=2,
    )
    await _mk_submission(
        db,
        session_id=s2.id,
        case_id="case_a",
        selected="send_as_is",
        duration_ms=6000,
        edit_distance=4,
    )
    # case_b: 2 send_as_is correct
    await _mk_submission(
        db,
        session_id=s1.id,
        case_id="case_b",
        selected="send_as_is",
        duration_ms=2000,
        edit_distance=0,
    )
    await _mk_submission(
        db,
        session_id=s2.id,
        case_id="case_b",
        selected="send_as_is",
        duration_ms=2000,
        edit_distance=0,
    )
    await db.commit()

    result = await per_case_stats(db)
    by_id = {r["caseId"]: r for r in result}
    assert set(by_id.keys()) == {"case_a", "case_b"}

    a = by_id["case_a"]
    assert a["defectPresent"] is True
    assert a["riskLevel"] == "high"
    assert a["goldAction"] == "escalate"
    assert a["goldActionZh"] == "升级处理"
    assert a["total"] == 2
    assert a["matchGold"] == 1
    assert a["unsafeSendAsIs"] == 1
    assert a["errorSurvival"] == 1
    assert a["appropriateEscalation"] == 1
    assert a["meanDurationMs"] == pytest.approx(5000)  # (4000+6000)/2
    assert a["meanEditDistance"] == pytest.approx(3)  # (2+4)/2

    b = by_id["case_b"]
    assert b["total"] == 2
    assert b["matchGold"] == 2
    assert b["unsafeSendAsIs"] == 0
    assert b["errorSurvival"] == 0
    assert b["appropriateEscalation"] == 0


@pytest.mark.asyncio
async def test_per_case_stats_null_durations_and_edit_distance(db: AsyncSession) -> None:
    """Division-by-zero safety: if all submissions for a case have NULL
    duration / edit_distance, the means must be 0 (not NaN or exception)."""
    await _mk_order_template(db)
    await _mk_case(db, case_id="c", gold="send_as_is")
    pt = await _mk_participant(db)
    sess = await _mk_session(db, participant_id=pt.id)
    await _mk_submission(
        db,
        session_id=sess.id,
        case_id="c",
        selected="send_as_is",
        duration_ms=None,
        edit_distance=None,
    )
    await db.commit()

    result = await per_case_stats(db)
    assert len(result) == 1
    assert result[0]["meanDurationMs"] == 0
    assert result[0]["meanEditDistance"] == 0
    assert result[0]["total"] == 1
    assert result[0]["matchGold"] == 1


@pytest.mark.asyncio
async def test_per_case_stats_excludes_practice(db: AsyncSession) -> None:
    await _mk_order_template(db)
    await _mk_case(db, case_id="practice", gold="send_as_is", is_practice=True)
    pt = await _mk_participant(db)
    sess = await _mk_session(db, participant_id=pt.id)
    await _mk_submission(db, session_id=sess.id, case_id="practice", selected="send_as_is")
    await db.commit()
    result = await per_case_stats(db)
    assert result == []


# ---------------------------------------------------------------------------
# per_participant_stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_per_participant_stats_empty(db: AsyncSession) -> None:
    assert await per_participant_stats(db) == []


@pytest.mark.asyncio
async def test_per_participant_stats_aggregates(db: AsyncSession) -> None:
    await _mk_order_template(db)
    await _mk_case(db, case_id="c1", gold="escalate", defect_present=True)
    await _mk_case(
        db, case_id="c2", gold="edit_then_send", alternates=["discard_and_rewrite"]
    )

    pt = await _mk_participant(db, condition="guardrail")
    sess = await _mk_session(db, participant_id=pt.id)
    # c1: correct escalate
    await _mk_submission(
        db, session_id=sess.id, case_id="c1", selected="escalate", duration_ms=3000
    )
    # c2: chose alternate — accuracy-correct, gold-incorrect
    await _mk_submission(
        db,
        session_id=sess.id,
        case_id="c2",
        selected="discard_and_rewrite",
        duration_ms=5000,
        edit_distance=10,
    )
    await db.commit()

    result = await per_participant_stats(db)
    assert len(result) == 1
    row = result[0]
    assert row["participantId"] == pt.id
    assert row["condition"] == "guardrail"
    assert row["total"] == 2
    assert row["matchGold"] == 2  # alternate counts via _action_matches_gold
    assert row["accuracy"] == 1.0
    assert row["appropriateEscalationCount"] == 1
    assert row["errorSurvivalCount"] == 0
    assert row["meanDurationMs"] == pytest.approx(4000)
    assert row["meanEditDistance"] == pytest.approx(5)  # (0 + 10) / 2


@pytest.mark.asyncio
async def test_per_participant_stats_single_participant_no_action(
    db: AsyncSession,
) -> None:
    """Participant created + session created + presentation created, but NO Action:
    must not appear in per_participant_stats (formal_presentations filters it out)."""
    await _mk_order_template(db)
    await _mk_case(db, case_id="c", gold="send_as_is")
    pt = await _mk_participant(db)
    sess = await _mk_session(db, participant_id=pt.id)
    pres = CasePresentation(
        id=_uid(), session_id=sess.id, case_id="c", order_index=0
    )
    db.add(pres)
    await db.commit()

    result = await per_participant_stats(db)
    assert result == []


# ---------------------------------------------------------------------------
# session_formal_performance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_formal_performance_empty_session(db: AsyncSession) -> None:
    await _mk_order_template(db)
    pt = await _mk_participant(db)
    sess = await _mk_session(db, participant_id=pt.id)
    await db.commit()
    result = await session_formal_performance(db, sess.id)
    assert result == {"correct": 0, "total": 0, "accuracy": 0.0}


# ---------------------------------------------------------------------------
# _percentile (internal helper)
# ---------------------------------------------------------------------------


def test_percentile_empty() -> None:
    assert _percentile([], 0.5) == 0.0


def test_percentile_single_value() -> None:
    assert _percentile([42], 0.5) == 42.0
    assert _percentile([42], 0.95) == 42.0


def test_percentile_known_sequence() -> None:
    # On [1,2,3,4,5,6,7,8,9,10]: P50 → 5.5 (linear interp), P95 → 9.55
    vals = list(range(1, 11))
    assert _percentile(vals, 0.50) == pytest.approx(5.5)
    assert _percentile(vals, 0.95) == pytest.approx(9.55)
    assert _percentile(vals, 1.0) == 10.0
    assert _percentile(vals, 0.0) == 1.0


# ---------------------------------------------------------------------------
# llm_call_stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_call_stats_empty(db: AsyncSession) -> None:
    result = await llm_call_stats(db)
    assert result["totals"] == {
        "count": 0,
        "errors": 0,
        "errorRate": 0.0,
        "promptTokens": 0,
        "completionTokens": 0,
    }
    assert result["perPurpose"] == []


@pytest.mark.asyncio
async def test_llm_call_stats_mixed_purposes_and_errors(db: AsyncSession) -> None:
    # case_draft: 3 calls, 1 error, latencies 100/200/300
    db.add(
        LLMCall(
            id=_uid(),
            purpose="case_draft",
            provider="deepseek",
            model="deepseek-chat",
            prompt_text="x",
            response_text="ok",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=100,
        )
    )
    db.add(
        LLMCall(
            id=_uid(),
            purpose="case_draft",
            provider="deepseek",
            model="deepseek-chat",
            prompt_text="x",
            response_text="ok",
            prompt_tokens=110,
            completion_tokens=55,
            latency_ms=200,
        )
    )
    db.add(
        LLMCall(
            id=_uid(),
            purpose="case_draft",
            provider="deepseek",
            model="deepseek-chat",
            prompt_text="x",
            response_text="",
            prompt_tokens=None,
            completion_tokens=None,
            latency_ms=300,
            error="timeout",
        )
    )
    # risk_tip: 1 call no error
    db.add(
        LLMCall(
            id=_uid(),
            purpose="risk_tip",
            provider="deepseek",
            model="deepseek-chat",
            prompt_text="x",
            response_text="ok",
            prompt_tokens=80,
            completion_tokens=20,
            latency_ms=150,
        )
    )
    await db.commit()

    result = await llm_call_stats(db)
    assert result["totals"]["count"] == 4
    assert result["totals"]["errors"] == 1
    assert result["totals"]["errorRate"] == 0.25
    assert result["totals"]["promptTokens"] == 290  # 100+110+0+80
    assert result["totals"]["completionTokens"] == 125  # 50+55+0+20

    by_purpose = {r["purpose"]: r for r in result["perPurpose"]}
    assert set(by_purpose.keys()) == {"case_draft", "risk_tip"}

    cd = by_purpose["case_draft"]
    assert cd["count"] == 3
    assert cd["errorRate"] == pytest.approx(1 / 3)
    assert cd["p50Ms"] == 200  # median of [100,200,300]
    assert cd["promptTokens"] == 210
    assert cd["completionTokens"] == 105

    rt = by_purpose["risk_tip"]
    assert rt["count"] == 1
    assert rt["errorRate"] == 0.0
    assert rt["p50Ms"] == 150
    assert rt["p95Ms"] == 150


# ---------------------------------------------------------------------------
# completion_timeseries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_completion_timeseries_empty(db: AsyncSession) -> None:
    assert await completion_timeseries(db) == []


@pytest.mark.asyncio
async def test_completion_timeseries_bucket_hour(db: AsyncSession) -> None:
    """Three sessions in two hour buckets; one completes."""
    await _mk_order_template(db)
    pt = await _mk_participant(db)
    t0 = datetime.now(timezone.utc).replace(minute=15, second=0, microsecond=0)
    t1 = t0 - timedelta(hours=1)  # previous hour
    # Session 1: started t0, completed t0+30min (same bucket)
    s1 = SessionModel(id=_uid(), participant_id=pt.id, status="completed")
    s1.started_at = t0
    s1.ended_at = t0 + timedelta(minutes=30)
    db.add(s1)
    # Session 2: started t0, no end
    s2 = SessionModel(id=_uid(), participant_id=pt.id, status="active")
    s2.started_at = t0 + timedelta(minutes=5)
    db.add(s2)
    # Session 3: started t1 (previous hour), no end
    s3 = SessionModel(id=_uid(), participant_id=pt.id, status="active")
    s3.started_at = t1
    db.add(s3)
    await db.commit()

    result = await completion_timeseries(db, bucket="hour")
    # Two buckets emitted (sorted ascending). t1 first, t0 second.
    assert len(result) == 2
    assert result[0]["started"] == 1  # t1 hour
    assert result[0]["completed"] == 0
    assert result[1]["started"] == 2  # t0 hour
    assert result[1]["completed"] == 1


@pytest.mark.asyncio
async def test_completion_timeseries_bucket_day(db: AsyncSession) -> None:
    await _mk_order_template(db)
    pt = await _mk_participant(db)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    s = SessionModel(id=_uid(), participant_id=pt.id, status="completed")
    s.started_at = today + timedelta(hours=5)
    s.ended_at = today + timedelta(hours=6)
    db.add(s)
    await db.commit()

    result = await completion_timeseries(db, bucket="day")
    assert len(result) == 1
    assert result[0]["started"] == 1
    assert result[0]["completed"] == 1


# ---------------------------------------------------------------------------
# log_stats_by_condition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_stats_by_condition_empty(db: AsyncSession) -> None:
    result = await log_stats_by_condition(db)
    assert result["conditions"] == ["plain", "guardrail"]
    # Every metric present, both conditions, n=0, mean=0
    keys = {m["key"] for m in result["metrics"]}
    assert "log_help_risk_panel" in keys
    assert "log_scroll_dwell_draft_section_dwell_sec" in keys
    for m in result["metrics"]:
        assert m["plain"] == {"mean": 0.0, "n": 0}
        assert m["guardrail"] == {"mean": 0.0, "n": 0}


@pytest.mark.asyncio
async def test_log_stats_by_condition_compares_two_conditions(
    db: AsyncSession,
) -> None:
    """Core research signal — guardrail participants open the help panel
    more often than plain, on average."""
    await _mk_order_template(db)
    await _mk_case(db, case_id="c", gold="edit_then_send", defect_present=True)

    pt_plain = await _mk_participant(db, condition="plain")
    pt_guard = await _mk_participant(db, condition="guardrail")
    s_plain = await _mk_session(db, participant_id=pt_plain.id)
    s_guard = await _mk_session(db, participant_id=pt_guard.id)

    # plain: did NOT open help panel; guardrail: did
    pres_p, act_p = await _mk_submission(
        db, session_id=s_plain.id, case_id="c", selected="edit_then_send"
    )
    act_p.client_stats = {
        "log_help_risk_panel": 0,
        "log_verification_clicks": 1,
        "log_case_review_time": 12.0,
    }
    pres_g, act_g = await _mk_submission(
        db, session_id=s_guard.id, case_id="c", selected="edit_then_send"
    )
    act_g.client_stats = {
        "log_help_risk_panel": 1,
        "log_verification_clicks": 5,
        "log_case_review_time": 28.0,
        "log_scroll_dwell_draft": {"section_dwell_sec": 3.5},
    }
    await db.commit()

    result = await log_stats_by_condition(db)
    by_key = {m["key"]: m for m in result["metrics"]}

    assert by_key["log_help_risk_panel"]["plain"] == {"mean": 0.0, "n": 1}
    assert by_key["log_help_risk_panel"]["guardrail"] == {"mean": 1.0, "n": 1}
    assert by_key["log_verification_clicks"]["plain"]["mean"] == 1.0
    assert by_key["log_verification_clicks"]["guardrail"]["mean"] == 5.0
    # nested dwell flattened
    assert by_key["log_scroll_dwell_draft_section_dwell_sec"]["guardrail"] == {
        "mean": 3.5,
        "n": 1,
    }
    assert by_key["log_scroll_dwell_draft_section_dwell_sec"]["plain"]["n"] == 0


@pytest.mark.asyncio
async def test_log_stats_by_condition_handles_missing_client_stats(
    db: AsyncSession,
) -> None:
    await _mk_order_template(db)
    await _mk_case(db, case_id="c", gold="send_as_is")
    pt = await _mk_participant(db, condition="plain")
    sess = await _mk_session(db, participant_id=pt.id)
    pres, act = await _mk_submission(
        db, session_id=sess.id, case_id="c", selected="send_as_is"
    )
    act.client_stats = None  # missing entirely
    await db.commit()
    result = await log_stats_by_condition(db)
    by_key = {m["key"]: m for m in result["metrics"]}
    # Should not raise; every key just has n=0
    assert by_key["log_help_risk_panel"]["plain"]["n"] == 0


# ---------------------------------------------------------------------------
# ui_event_frequency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ui_event_frequency_empty(db: AsyncSession) -> None:
    assert await ui_event_frequency(db) == []


@pytest.mark.asyncio
async def test_ui_event_frequency_by_condition(db: AsyncSession) -> None:
    await _mk_order_template(db)
    pt_plain = await _mk_participant(db, condition="plain")
    pt_guard = await _mk_participant(db, condition="guardrail")
    s_p = await _mk_session(db, participant_id=pt_plain.id)
    s_g = await _mk_session(db, participant_id=pt_guard.id)
    # 2 events for plain; 3 events for guardrail; mix of types
    db.add_all(
        [
            UiEvent(
                id=_uid(),
                session_id=s_p.id,
                event_type="chart_expanded",
                payload={},
            ),
            UiEvent(
                id=_uid(),
                session_id=s_p.id,
                event_type="panel_clicked",
                payload={},
            ),
            UiEvent(
                id=_uid(),
                session_id=s_g.id,
                event_type="chart_expanded",
                payload={},
            ),
            UiEvent(
                id=_uid(),
                session_id=s_g.id,
                event_type="help_risk_panel_expanded",
                payload={},
            ),
            UiEvent(
                id=_uid(),
                session_id=s_g.id,
                event_type="help_risk_panel_expanded",
                payload={},
            ),
        ]
    )
    await db.commit()

    result = await ui_event_frequency(db, by="condition")
    by_type = {r["eventType"]: r for r in result}

    assert by_type["chart_expanded"]["count"] == 2
    assert by_type["chart_expanded"]["splits"] == {"plain": 1, "guardrail": 1}
    assert by_type["help_risk_panel_expanded"]["count"] == 2
    assert by_type["help_risk_panel_expanded"]["splits"] == {"guardrail": 2}
    assert by_type["panel_clicked"]["count"] == 1
    # result sorted by count descending
    assert result[0]["count"] >= result[-1]["count"]


# ---------------------------------------------------------------------------
# active_sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_sessions_none_active(db: AsyncSession) -> None:
    await _mk_order_template(db)
    pt = await _mk_participant(db, completed=True)
    s = SessionModel(id=_uid(), participant_id=pt.id, status="completed")
    s.ended_at = datetime.now(timezone.utc)
    db.add(s)
    await db.commit()
    assert await active_sessions(db) == []


@pytest.mark.asyncio
async def test_active_sessions_returns_latest_event_per_session(db: AsyncSession) -> None:
    await _mk_order_template(db)
    pt = await _mk_participant(db, condition="guardrail")
    sess = await _mk_session(db, participant_id=pt.id)
    earlier = datetime.now(timezone.utc) - timedelta(minutes=10)
    later = datetime.now(timezone.utc) - timedelta(minutes=2)
    ev_old = UiEvent(
        id=_uid(),
        session_id=sess.id,
        event_type="case_view_start",
        payload={},
    )
    ev_old.server_ts = earlier
    ev_new = UiEvent(
        id=_uid(),
        session_id=sess.id,
        event_type="chart_expanded",
        payload={},
    )
    ev_new.server_ts = later
    db.add_all([ev_old, ev_new])
    await db.commit()

    result = await active_sessions(db)
    assert len(result) == 1
    row = result[0]
    assert row["sessionId"] == sess.id
    assert row["condition"] == "guardrail"
    assert row["lastEventType"] == "chart_expanded"  # the LATER one wins
    assert row["elapsedMs"] > 0


@pytest.mark.asyncio
async def test_session_formal_performance_filters_practice_and_no_action(
    db: AsyncSession,
) -> None:
    """A session with practice + formal submissions + a presentation without action:
    only formal+with-action should count."""
    await _mk_order_template(db)
    await _mk_case(db, case_id="practice", gold="send_as_is", is_practice=True)
    await _mk_case(db, case_id="formal_1", gold="escalate", defect_present=True)
    await _mk_case(db, case_id="formal_2", gold="send_as_is")

    pt = await _mk_participant(db)
    sess = await _mk_session(db, participant_id=pt.id)
    # practice submission (should be filtered)
    await _mk_submission(db, session_id=sess.id, case_id="practice", selected="send_as_is")
    # formal correct
    await _mk_submission(db, session_id=sess.id, case_id="formal_1", selected="escalate")
    # formal wrong
    await _mk_submission(db, session_id=sess.id, case_id="formal_2", selected="escalate")
    await db.commit()

    result = await session_formal_performance(db, sess.id)
    assert result == {
        "correct": 1,
        "total": 2,
        "accuracy": 0.5,
    }
