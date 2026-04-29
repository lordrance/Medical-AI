from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Action,
    Case,
    CasePresentation,
    Participant,
    Session,
)
from app.schemas.common import ACTION_LABEL_ZH

ALL_ACTIONS: list[str] = [
    "send_as_is",
    "edit_then_send",
    "discard_and_rewrite",
    "escalate",
]


def _action_matches_gold(case: Case, selected: str) -> bool:
    alts = case.gold_action_alternates or []
    return selected == case.gold_action or selected in alts


def _dedupe_presentations_by_session_case(
    rows: list[CasePresentation],
) -> list[CasePresentation]:
    """If the same case was submitted more than once (e.g. browser back), keep latest."""
    best: dict[tuple[str, str], CasePresentation] = {}
    for p in rows:
        if p.action is None:
            continue
        key = (p.session_id, p.case_id)
        other = best.get(key)
        if other is None:
            best[key] = p
            continue
        t_new = p.action.server_received_at
        t_old = other.action.server_received_at  # type: ignore[union-attr]
        if t_new > t_old:
            best[key] = p
    return list(best.values())


async def session_formal_performance(
    db: AsyncSession, session_id: str
) -> dict[str, Any]:
    """Count formal-case correct vs gold or alternates (same rule as admin export)."""
    stmt = (
        select(CasePresentation)
        .join(Action, Action.case_presentation_id == CasePresentation.id)
        .where(CasePresentation.session_id == session_id)
        .options(
            selectinload(CasePresentation.case),
            selectinload(CasePresentation.action),
        )
    )
    rows = (await db.execute(stmt)).scalars().all()
    formal = [r for r in rows if r.case is not None and not r.case.is_practice]
    formal = _dedupe_presentations_by_session_case(
        [p for p in formal if p.action is not None]
    )
    correct = 0
    for p in formal:
        assert p.case is not None and p.action is not None
        if _action_matches_gold(p.case, p.action.selected_action):
            correct += 1
    total = len(formal)
    return {
        "correct": correct,
        "total": total,
        "accuracy": (correct / total) if total else 0.0,
    }


async def completion_stats(db: AsyncSession) -> dict[str, Any]:
    total = (await db.execute(select(func.count(Participant.id)))).scalar() or 0
    completed = (
        await db.execute(
            select(func.count(Participant.id)).where(Participant.completed_flag.is_(True))
        )
    ).scalar() or 0
    by_cond_rows = (
        await db.execute(
            select(Participant.condition, func.count(Participant.id)).group_by(
                Participant.condition
            )
        )
    ).all()
    return {
        "totalParticipants": total,
        "completed": completed,
        "completionRate": completed / total if total else 0.0,
        "byCondition": [{"condition": c, "count": n} for c, n in by_cond_rows],
    }


async def _formal_presentations(db: AsyncSession) -> list[CasePresentation]:
    stmt = (
        select(CasePresentation)
        .options(
            selectinload(CasePresentation.case),
            selectinload(CasePresentation.action),
            selectinload(CasePresentation.session).selectinload(Session.participant),
        )
    )
    rows = (await db.execute(stmt)).scalars().all()
    filtered = [
        r
        for r in rows
        if r.case is not None and not r.case.is_practice and r.action is not None
    ]
    return _dedupe_presentations_by_session_case(filtered)


async def confusion_matrix(db: AsyncSession) -> dict[str, Any]:
    rows = await _formal_presentations(db)
    actions = ALL_ACTIONS
    idx = {a: i for i, a in enumerate(actions)}
    matrix = [[0] * len(actions) for _ in actions]
    correct = 0
    total = 0
    for r in rows:
        gold = r.case.gold_action
        sel = r.action.selected_action  # type: ignore[union-attr]
        if gold not in idx or sel not in idx:
            continue
        matrix[idx[gold]][idx[sel]] += 1
        total += 1
        if gold == sel:
            correct += 1
    return {
        "actions": actions,
        "actionsZh": [ACTION_LABEL_ZH[a] for a in actions],
        "matrix": matrix,
        "total": total,
        "accuracy": (correct / total) if total else 0.0,
    }


async def per_case_stats(db: AsyncSession) -> list[dict[str, Any]]:
    rows = await _formal_presentations(db)
    by_case: dict[str, list[CasePresentation]] = defaultdict(list)
    for r in rows:
        by_case[r.case_id].append(r)

    results: list[dict[str, Any]] = []
    for cid, group in by_case.items():
        c: Case = group[0].case  # type: ignore[assignment]
        gold = c.gold_action
        alts = c.gold_action_alternates or []

        match_gold = 0
        match_alt = 0
        unsafe_send = 0
        error_survival = 0
        appropriate_escalation = 0
        dur_sum = 0
        dur_n = 0
        ed_sum = 0
        ed_n = 0
        for p in group:
            a = p.action
            if a is None:
                continue
            if a.selected_action == gold:
                match_gold += 1
            if a.selected_action in alts:
                match_alt += 1
            if c.defect_present and a.send_as_is_flag:
                unsafe_send += 1
            if (
                c.defect_present
                and a.selected_action != gold
                and a.selected_action not in alts
            ):
                error_survival += 1
            if gold == "escalate" and a.escalate_flag:
                appropriate_escalation += 1
            if p.duration_ms is not None:
                dur_sum += p.duration_ms
                dur_n += 1
            if a.edit_distance is not None:
                ed_sum += a.edit_distance
                ed_n += 1
        results.append(
            {
                "caseId": cid,
                "defectPresent": c.defect_present,
                "riskLevel": c.risk_level,
                "goldAction": gold,
                "goldActionZh": ACTION_LABEL_ZH.get(gold, gold),
                "goldActionAlternates": alts,
                "total": len(group),
                "matchGold": match_gold,
                "matchAlternates": match_alt,
                "unsafeSendAsIs": unsafe_send,
                "errorSurvival": error_survival,
                "appropriateEscalation": appropriate_escalation,
                "meanDurationMs": (dur_sum / dur_n) if dur_n else 0,
                "meanEditDistance": (ed_sum / ed_n) if ed_n else 0,
            }
        )
    results.sort(key=lambda x: x["caseId"])
    return results


async def per_participant_stats(db: AsyncSession) -> list[dict[str, Any]]:
    rows = await _formal_presentations(db)
    by_pt: dict[str, list[CasePresentation]] = defaultdict(list)
    for r in rows:
        by_pt[r.session.participant_id].append(r)
    results = []
    for pid, group in by_pt.items():
        cond = group[0].session.participant.condition
        match_gold = 0
        total = 0
        error_survival = 0
        appropriate_escalation = 0
        dur_sum = 0
        dur_n = 0
        ed_sum = 0
        ed_n = 0
        for p in group:
            a = p.action
            c = p.case
            if a is None or c is None:
                continue
            total += 1
            alts = c.gold_action_alternates or []
            gold = c.gold_action
            sel = a.selected_action
            if sel == gold:
                match_gold += 1
            if c.defect_present and sel != gold and sel not in alts:
                error_survival += 1
            if gold == "escalate" and a.escalate_flag:
                appropriate_escalation += 1
            if p.duration_ms is not None:
                dur_sum += p.duration_ms
                dur_n += 1
            if a.edit_distance is not None:
                ed_sum += a.edit_distance
                ed_n += 1
        results.append(
            {
                "participantId": pid,
                "condition": cond,
                "total": total,
                "matchGold": match_gold,
                "accuracy": match_gold / total if total else 0.0,
                "errorSurvivalCount": error_survival,
                "appropriateEscalationCount": appropriate_escalation,
                "meanDurationMs": dur_sum / dur_n if dur_n else 0,
                "meanEditDistance": ed_sum / ed_n if ed_n else 0,
            }
        )
    results.sort(key=lambda x: x["participantId"])
    return results
