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
    OrderTemplate,
    Participant,
    Session as SessionModel,
)
from app.db.session import get_session_factory
from app.services.analysis import (
    completion_stats,
    confusion_matrix,
    per_case_stats,
    per_participant_stats,
    session_formal_performance,
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
