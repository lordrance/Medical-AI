from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from datetime import datetime, timedelta, timezone

from app.db.models import (
    Action,
    Case,
    CasePresentation,
    LLMCall,
    Participant,
    Session,
    UiEvent,
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
        c = r.case
        sel = r.action.selected_action  # type: ignore[union-attr]
        gold = c.gold_action
        if gold not in idx or sel not in idx:
            continue
        matrix[idx[gold]][idx[sel]] += 1
        total += 1
        if _action_matches_gold(c, sel):
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
            sel = a.selected_action
            if _action_matches_gold(c, sel):
                match_gold += 1
            alts = c.gold_action_alternates or []
            gold = c.gold_action
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


# ---------------------------------------------------------------------------
# Dashboard aggregations (Phase A.2): functions powering /api/admin/dashboard/*
# All time bucketing / percentile maths is done in Python (data volume in HCI
# studies is small) to avoid SQLite-vs-Postgres dialect divergence.
# ---------------------------------------------------------------------------


def _percentile(sorted_vals: list[int], q: float) -> float:
    """Linear-interpolation percentile on a SORTED list. q in [0, 1]."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _as_utc(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes even when the column is tz-aware.
    Normalise so comparisons against `datetime.now(timezone.utc)` don't raise."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def llm_call_stats(db: AsyncSession) -> dict[str, Any]:
    """LLM operational health: per-purpose latency p50/p95, token totals,
    error rate, and recent-24h call counts.

    Returns:
        {
          "totals": {"count": int, "errors": int, "errorRate": float,
                     "promptTokens": int, "completionTokens": int},
          "perPurpose": [
              {"purpose": str, "count": int, "errorRate": float,
               "p50Ms": float, "p95Ms": float, "promptTokens": int,
               "completionTokens": int, "count24h": int},
              ...
          ]
        }
    """
    rows = (await db.execute(select(LLMCall))).scalars().all()

    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)

    total_count = len(rows)
    total_errors = sum(1 for r in rows if r.error)
    total_prompt = sum(r.prompt_tokens or 0 for r in rows)
    total_completion = sum(r.completion_tokens or 0 for r in rows)

    by_purpose: dict[str, list[LLMCall]] = defaultdict(list)
    for r in rows:
        by_purpose[r.purpose].append(r)

    per_purpose: list[dict[str, Any]] = []
    for purpose, group in by_purpose.items():
        latencies = sorted(r.latency_ms or 0 for r in group)
        errors = sum(1 for r in group if r.error)
        per_purpose.append(
            {
                "purpose": purpose,
                "count": len(group),
                "errorRate": errors / len(group) if group else 0.0,
                "p50Ms": _percentile(latencies, 0.50),
                "p95Ms": _percentile(latencies, 0.95),
                "promptTokens": sum(r.prompt_tokens or 0 for r in group),
                "completionTokens": sum(r.completion_tokens or 0 for r in group),
                "count24h": sum(
                    1
                    for r in group
                    if _as_utc(r.created_at) is not None
                    and _as_utc(r.created_at) >= cutoff_24h  # type: ignore[operator]
                ),
            }
        )
    per_purpose.sort(key=lambda x: x["purpose"])

    return {
        "totals": {
            "count": total_count,
            "errors": total_errors,
            "errorRate": (total_errors / total_count) if total_count else 0.0,
            "promptTokens": total_prompt,
            "completionTokens": total_completion,
        },
        "perPurpose": per_purpose,
    }


def _bucket_dt(dt: datetime, bucket: str) -> str:
    """Truncate a datetime to a bucket boundary and return an ISO-8601 string.
    bucket ∈ {'hour', 'day'}. Always emits UTC."""
    dt = dt.astimezone(timezone.utc)
    if bucket == "day":
        truncated = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    else:  # hour (default)
        truncated = dt.replace(minute=0, second=0, microsecond=0)
    return truncated.isoformat()


async def completion_timeseries(
    db: AsyncSession, bucket: str = "hour", window_hours: int = 168
) -> list[dict[str, Any]]:
    """Sessions started/completed per time bucket over the last `window_hours`.

    Returns a list sorted by bucket ascending. Empty buckets are omitted; the
    frontend can fill gaps if needed. bucket ∈ {'hour', 'day'}.
    """
    if bucket not in ("hour", "day"):
        bucket = "hour"

    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    # Filter in Python so SQLite (which stores tz-naive) and Postgres both work.
    rows = (await db.execute(select(Session))).scalars().all()
    rows = [r for r in rows if (_as_utc(r.started_at) or cutoff) >= cutoff]

    by_bucket: dict[str, dict[str, int]] = defaultdict(
        lambda: {"started": 0, "completed": 0}
    )
    for s in rows:
        started = _as_utc(s.started_at)
        if started is None:
            continue
        by_bucket[_bucket_dt(started, bucket)]["started"] += 1
        ended = _as_utc(s.ended_at)
        if ended is not None:
            by_bucket[_bucket_dt(ended, bucket)]["completed"] += 1

    return [
        {"ts": ts, "started": v["started"], "completed": v["completed"]}
        for ts, v in sorted(by_bucket.items())
    ]


# Keys we surface in the by-condition comparison. Only the scalar `log_*`
# entries from build_pdf_autolog_client_stats — the nested `log_scroll_dwell_draft`
# object is exposed separately as section_dwell_sec.
_LOG_STATS_KEYS_SCALAR: tuple[str, ...] = (
    "log_case_review_time",
    "log_time_to_first_action",
    "log_edit_actions",
    "log_source_panel_open",
    "log_help_risk_panel",
    "log_toggle_draft_source",
    "log_verification_clicks",
)


async def log_stats_by_condition(db: AsyncSession) -> dict[str, Any]:
    """Per-condition averages of the log_* fields in actions.client_stats.

    This is the core research signal — comparing guardrail vs plain on
    verification and help-panel-usage behaviours. Practice cases excluded.

    Returns:
        {
          "conditions": ["plain", "guardrail"],
          "metrics": [
              {"key": "log_help_risk_panel",
               "plain":   {"mean": float, "n": int},
               "guardrail": {"mean": float, "n": int}},
              ...
              {"key": "log_scroll_dwell_draft_section_dwell_sec", ...},
          ]
        }
    """
    formal = await _formal_presentations(db)

    by_cond_values: dict[str, dict[str, list[float]]] = {
        "plain": defaultdict(list),
        "guardrail": defaultdict(list),
    }

    for p in formal:
        sess = p.session
        if sess is None or sess.participant is None:
            continue
        cond = sess.participant.condition
        if cond not in by_cond_values:
            continue
        cs = (p.action.client_stats or {}) if p.action is not None else {}
        if not isinstance(cs, dict):
            continue
        for k in _LOG_STATS_KEYS_SCALAR:
            v = cs.get(k)
            if isinstance(v, (int, float)):
                by_cond_values[cond][k].append(float(v))
        scroll = cs.get("log_scroll_dwell_draft")
        if isinstance(scroll, dict):
            sec = scroll.get("section_dwell_sec")
            if isinstance(sec, (int, float)):
                by_cond_values[cond]["log_scroll_dwell_draft_section_dwell_sec"].append(
                    float(sec)
                )

    all_keys = list(_LOG_STATS_KEYS_SCALAR) + [
        "log_scroll_dwell_draft_section_dwell_sec"
    ]
    metrics: list[dict[str, Any]] = []
    for k in all_keys:
        row: dict[str, Any] = {"key": k}
        for cond in ("plain", "guardrail"):
            vals = by_cond_values[cond][k]
            row[cond] = {
                "mean": (sum(vals) / len(vals)) if vals else 0.0,
                "n": len(vals),
            }
        metrics.append(row)

    return {"conditions": ["plain", "guardrail"], "metrics": metrics}


async def ui_event_frequency(
    db: AsyncSession, by: str = "condition"
) -> list[dict[str, Any]]:
    """Count of each event_type, optionally split by condition or by case.

    `by` ∈ {'condition', 'case', 'none'}.

    Returns a list of dicts: {"eventType": str, "count": int, splits: {...}}.
    """
    if by not in ("condition", "case", "none"):
        by = "condition"

    # Single query joining UiEvent → Session → Participant for condition,
    # and UiEvent → CasePresentation → Case for case_id (both via outer-join
    # because case_presentation_id is nullable on UiEvent).
    stmt = select(UiEvent).options(
        selectinload(UiEvent.session).selectinload(Session.participant),
        selectinload(UiEvent.presentation).selectinload(CasePresentation.case),
    )
    rows = (await db.execute(stmt)).scalars().all()

    counts: dict[str, int] = defaultdict(int)
    split_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for ev in rows:
        counts[ev.event_type] += 1
        if by == "condition":
            cond = (
                ev.session.participant.condition
                if ev.session is not None and ev.session.participant is not None
                else "unknown"
            )
            split_counts[ev.event_type][cond] += 1
        elif by == "case":
            cid = (
                ev.presentation.case_id
                if ev.presentation is not None
                else "no_case"
            )
            split_counts[ev.event_type][cid] += 1

    out: list[dict[str, Any]] = []
    for et, total in counts.items():
        row: dict[str, Any] = {"eventType": et, "count": total}
        if by != "none":
            row["splits"] = dict(split_counts[et])
        out.append(row)
    out.sort(key=lambda x: x["count"], reverse=True)
    return out


async def active_sessions(db: AsyncSession) -> list[dict[str, Any]]:
    """Sessions with status != 'completed': in-progress experiments.

    Returns elapsed time since start, the timestamp of the last UI event,
    and the most recent event_type so researchers can spot stuck sessions.
    """
    sessions = (
        await db.execute(
            select(Session)
            .where(Session.status != "completed")
            .options(selectinload(Session.participant))
        )
    ).scalars().all()
    if not sessions:
        return []

    # Fetch the most-recent UiEvent per session in one query.
    session_ids = [s.id for s in sessions]
    last_event_rows = (
        await db.execute(
            select(UiEvent).where(UiEvent.session_id.in_(session_ids))
        )
    ).scalars().all()
    latest_by_session: dict[str, UiEvent] = {}
    for ev in last_event_rows:
        cur = latest_by_session.get(ev.session_id)
        if cur is None or ev.server_ts > cur.server_ts:
            latest_by_session[ev.session_id] = ev

    now = datetime.now(timezone.utc)
    out: list[dict[str, Any]] = []
    for s in sessions:
        last = latest_by_session.get(s.id)
        started = _as_utc(s.started_at)
        out.append(
            {
                "sessionId": s.id,
                "participantId": s.participant_id,
                "condition": s.participant.condition if s.participant else None,
                "startedAt": started.isoformat() if started else None,
                "elapsedMs": int((now - started).total_seconds() * 1000)
                if started
                else 0,
                "lastEventAt": (
                    _as_utc(last.server_ts).isoformat()  # type: ignore[union-attr]
                    if last and last.server_ts
                    else None
                ),
                "lastEventType": last.event_type if last else None,
            }
        )
    out.sort(key=lambda x: x["startedAt"] or "", reverse=True)
    return out
