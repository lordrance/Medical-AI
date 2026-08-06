"""
================================================================================
文件作用：★ 研究统计的核心 —— 论文里的数字都是这里算出来的
================================================================================

这个文件把数据库里一行行原始记录，变成论文能用的指标。
它不碰 HTTP、不管前端，只做纯计算，所以最容易单独测试和复核。

被两个地方调用：
  * 管理后台的看板和数据导出（api/admin/ 下面几个文件）
  * 医生提交后测时，算「你答对了几道」显示在完成页上（api/survey.py）

--------------------------------------------------------------------------------
★ 判分规则（整个文件的基础）
--------------------------------------------------------------------------------
医生选的处理方式，只要满足下面任一条就算「答对」：
    1. 正好是 gold_action（研究团队认为最恰当的做法）
    2. 在 gold_action_alternates 里（次优但也可接受的做法）

比如一道该「弃用并重写」的题，医生选了「上报」也算合理，不算错。
这两个字段都定义在 backend/data/cases.json 里。

--------------------------------------------------------------------------------
本文件的代码块（从上到下）：
--------------------------------------------------------------------------------
  第 1 块  ALL_ACTIONS                        四种处理方式的固定顺序
  第 2 块  _action_matches_gold()             ★ 判分规则本身
  第 3 块  _dedupe_presentations_by_session_case()  去掉历史遗留的重复记录
  第 4 块  session_formal_performance()       某个人答对几道（完成页用）
  第 5 块  completion_stats()                 总人数 / 完成人数
  第 6 块  _formal_presentations()            取出全部"已作答的正式题"
  第 7 块  confusion_matrix()                 ★ 混淆矩阵（论文最核心的表）
  第 8 块  per_case_stats()                   ★ 每道题的统计
  第 9 块  per_participant_stats()            ★ 每个人的统计
  第10 块  _percentile() / _as_utc()          两个小工具
  第11 块  llm_call_stats()                   AI 调用统计
  第12 块  _bucket_dt() / completion_timeseries()  完成人数随时间的曲线
  第13 块  log_stats_overall()                整体行为指标
  第14 块  ui_event_frequency()               行为埋点频次（热力图）
  第15 块  active_sessions()                  当前谁在线答题
================================================================================
"""

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

# ── 第 1 块：四种处理方式的固定顺序 ──────────────────────────────────────
# ★ 顺序很重要：混淆矩阵的行列都按这个顺序排，改了顺序矩阵就错位了。
ALL_ACTIONS: list[str] = [
    "send_as_is",
    "edit_then_send",
    "discard_and_rewrite",
    "escalate",
]


# ── 第 2 块：判分规则 ★ ──────────────────────────────────────────────────
def _action_matches_gold(case: Case, selected: str) -> bool:
    """★ 判分规则：这道题答对了吗？

    答对 = 选的正好是标准答案，或者选的在「次优可接受」列表里。
    比如一道该「弃用并重写」的题，医生选了「上报」也算合理，不算错。
    每道题的 goldActionAlternates 至少有一个，在 cases.json 里定义。
    """
    alts = case.gold_action_alternates or []
    return selected == case.gold_action or selected in alts


# ── 第 3 块：去重 ────────────────────────────────────────────────────────
def _dedupe_presentations_by_session_case(
    rows: list[CasePresentation],
) -> list[CasePresentation]:
    """If the same case was submitted more than once (e.g. browser back), keep latest.

    中文：同一个人的同一道题如果有多条记录，只留最新那条，避免重复计数。

    ★ 这是历史遗留的防御性代码：早期 /api/case/open 有并发 bug，
    生产库里积累了 23 组重复行。现在源头已由 session_write_lock 堵住
    （见 db/locks.py），但老数据还在，所以这个去重必须保留。
    """
    best: dict[tuple[str, str], CasePresentation] = {}
    for p in rows:
        if p.action is None:
            continue  # 没作答的记录不参与统计
        key = (p.session_id, p.case_id)  # 用「谁 + 哪道题」做去重键
        other = best.get(key)
        if other is None:
            best[key] = p
            continue
        # 同一个键出现两次 → 比较服务器收到的时间，留晚的那条
        t_new = p.action.server_received_at
        t_old = other.action.server_received_at  # type: ignore[union-attr]
        if t_new > t_old:
            best[key] = p
    return list(best.values())


# ── 第 4 块：某个人答对几道 ──────────────────────────────────────────────
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


# ── 第 5 块：完成率 ──────────────────────────────────────────────────────
async def completion_stats(db: AsyncSession) -> dict[str, Any]:
    """总共多少人开始了、多少人做完了。后台首页那两个数字。"""
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


# ── 第 6 块：取出全部已作答的正式题 ──────────────────────────────────────
async def _formal_presentations(db: AsyncSession) -> list[CasePresentation]:
    """取出全部「已作答的正式题」记录，供下面各个统计函数复用。

    做了三层过滤：题目存在、不是练习题、已经作答。最后再去重。
    selectinload 是一次性把关联的 case / action / session / participant
    都查出来，避免后面循环里每条再查一次数据库（N+1 查询问题）。
    """
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


# ── 第 7 块：混淆矩阵 ★ 论文最核心的一张表 ──────────────────────────────
async def confusion_matrix(db: AsyncSession) -> dict[str, Any]:
    """★ 混淆矩阵：标准答案（行）vs 医生实际选择（列）。

    这是论文里最核心的一张表。举例，matrix[2][0] = 5 表示：
    有 5 次，标准答案是「弃用并重写」，但医生选了「原样发送」——
    这就是最危险的过度信任 AI 的情况。

    对角线 = 选对了；右上/左下 = 选错了，错的方向还能看出是保守还是激进。
    """
    rows = await _formal_presentations(db)
    actions = ALL_ACTIONS
    idx = {a: i for i, a in enumerate(actions)}  # 动作名 → 矩阵下标
    matrix = [[0] * len(actions) for _ in actions]  # 4×4 全零方阵
    correct = 0
    total = 0
    for r in rows:
        c = r.case
        sel = r.action.selected_action  # type: ignore[union-attr]  医生选的
        gold = c.gold_action                                        # 标准答案
        if gold not in idx or sel not in idx:
            continue  # 出现了枚举外的值（脏数据），跳过不统计
        matrix[idx[gold]][idx[sel]] += 1  # 行=标准答案，列=实际选择
        total += 1
        # 注意：准确率用的是「含次优答案」的宽松判定，
        # 而矩阵本身记的是严格的原始分布。两者口径不同是故意的。
        if _action_matches_gold(c, sel):
            correct += 1
    return {
        "actions": actions,
        "actionsZh": [ACTION_LABEL_ZH[a] for a in actions],
        "matrix": matrix,
        "total": total,
        "accuracy": (correct / total) if total else 0.0,
    }


# ── 第 8 块：每道题的统计 ★ ─────────────────────────────────────────────
async def per_case_stats(db: AsyncSession) -> list[dict[str, Any]]:
    """按题目分组统计。用来回答"哪道题最多人栽跟头"。"""
    rows = await _formal_presentations(db)
    by_case: dict[str, list[CasePresentation]] = defaultdict(list)
    for r in rows:
        by_case[r.case_id].append(r)

    results: list[dict[str, Any]] = []
    for cid, group in by_case.items():
        c: Case = group[0].case  # type: ignore[assignment]
        gold = c.gold_action
        alts = c.gold_action_alternates or []

        # 下面这些计数器就是每道题要算的指标，含义见 results 里的键名注释。
        match_gold = 0              # 选中标准答案的次数
        match_alt = 0               # 选中次优答案的次数
        unsafe_send = 0             # ★ 危险的原样发送
        error_survival = 0          # ★ AI 的错误「存活」下来
        appropriate_escalation = 0  # 该上报时确实上报了
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

            # ★ unsafeSendAsIs：AI 草稿里明明埋了错，医生却选了「原样发送」。
            # 这是本研究最关键的风险指标——AI 的错误被原封不动发给了患者。
            if c.defect_present and a.send_as_is_flag:
                unsafe_send += 1

            # ★ errorSurvival：AI 有错，而医生的处理方式既不是标准答案
            # 也不是次优答案 —— 也就是这个错误没有被恰当地拦下来。
            # 比 unsafeSendAsIs 范围更宽（改了几个字但没改到点子上也算）。
            if (
                c.defect_present
                and a.selected_action != gold
                and a.selected_action not in alts
            ):
                error_survival += 1

            # 该上报的题（比如患者描述了危急症状）里，有多少人真的上报了
            if gold == "escalate" and a.escalate_flag:
                appropriate_escalation += 1

            # 用时和编辑距离要单独计数，因为可能为空，不能直接除以 len(group)
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


# ── 第 9 块：每个人的统计 ★ ─────────────────────────────────────────────
async def per_participant_stats(db: AsyncSession) -> list[dict[str, Any]]:
    """按人分组统计。用来回答"谁在敷衍了事"——
    比如某人 8 道题全选原样发送、平均每题只花 10 秒。"""
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


# ── 第 10 块：两个小工具 ─────────────────────────────────────────────────
def _percentile(sorted_vals: list[int], q: float) -> float:
    """Linear-interpolation percentile on a SORTED list. q in [0, 1].

    中文：算百分位数。q=0.5 就是中位数，q=0.95 就是 95 分位。
    传进来的列表**必须已经排好序**，函数自己不排（排序是调用方的事，
    避免同一份数据被反复排序）。

    ★ 为什么看中位数而不只看平均数：平均数会被极端值带偏。
    一个人挂机 2 小时，能把全组的"平均用时"抬高一大截，
    而中位数几乎不受影响，更能代表"典型的医生"。
    """
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


# ── 第 11 块：AI 调用统计 ────────────────────────────────────────────────
async def llm_call_stats(db: AsyncSession) -> dict[str, Any]:
    """LLM operational health: per-purpose latency p50/p95, token totals,
    error rate, and recent-24h call counts.

    中文：AI 调用了多少次、失败多少、多慢。
    ★ V4 医生端完全不调 AI，所以生产环境这里通常全是 0。

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


# ── 第 12 块：时间曲线 ───────────────────────────────────────────────────
def _bucket_dt(dt: datetime, bucket: str) -> str:
    """Truncate a datetime to a bucket boundary and return an ISO-8601 string.
    bucket ∈ {'hour', 'day'}. Always emits UTC.

    中文：把一个时刻归到"哪个小时"或"哪一天"这个格子里，用来画曲线。
    比如 14:37 按小时归到 14:00。统一转成 UTC 再归位，
    否则跨时区的数据会落到错误的格子里。
    """
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


# ── 第 13 块：整体行为指标 ──────────────────────────────────────────────
async def log_stats_overall(db: AsyncSession) -> dict[str, Any]:
    """Cohort-wide averages of the log_* fields in actions.client_stats.

    V4: single-condition study, so the V3 by-condition comparison
    collapses to one column. Practice cases excluded.

    中文：全体医生的平均用时、平均编辑距离、四种处理方式的分布等。
    只统计 8 道正式题，练习题不算。

    Returns:
        {
          "metrics": [
              {"key": "log_help_risk_panel", "mean": float, "n": int},
              ...
              {"key": "log_scroll_dwell_draft_section_dwell_sec", ...},
          ]
        }
    """
    formal = await _formal_presentations(db)

    values: dict[str, list[float]] = defaultdict(list)

    for p in formal:
        cs = (p.action.client_stats or {}) if p.action is not None else {}
        if not isinstance(cs, dict):
            continue
        for k in _LOG_STATS_KEYS_SCALAR:
            v = cs.get(k)
            if isinstance(v, (int, float)):
                values[k].append(float(v))
        scroll = cs.get("log_scroll_dwell_draft")
        if isinstance(scroll, dict):
            sec = scroll.get("section_dwell_sec")
            if isinstance(sec, (int, float)):
                values["log_scroll_dwell_draft_section_dwell_sec"].append(float(sec))

    all_keys = list(_LOG_STATS_KEYS_SCALAR) + [
        "log_scroll_dwell_draft_section_dwell_sec"
    ]
    metrics: list[dict[str, Any]] = []
    for k in all_keys:
        vals = values[k]
        metrics.append(
            {
                "key": k,
                "mean": (sum(vals) / len(vals)) if vals else 0.0,
                "n": len(vals),
            }
        )

    return {"metrics": metrics}


# ── 第 14 块：行为埋点频次 ──────────────────────────────────────────────
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


# ── 第 15 块：谁在线答题 ────────────────────────────────────────────────
async def active_sessions(db: AsyncSession) -> list[dict[str, Any]]:
    """Sessions with status != 'completed': in-progress experiments.

    Returns elapsed time since start, the timestamp of the last UI event,
    and the most recent event_type so researchers can spot stuck sessions.

    ★ 中文：发放问卷期间最有用的一个接口——实时看到有几个人正在做、
    做到第几题了、最后一次动作是什么时候。
    如果某人最后动作停在 20 分钟前，多半是卡住或放弃了。
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
