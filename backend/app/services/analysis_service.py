"""Service layer for aggregation queries.

Wraps the existing analysis module functions into a class that consumes
repository objects so callers don't need to know about SQLAlchemy sessions.
"""

from __future__ import annotations

from typing import Any

from app.repositories.action_repo import ActionRepo
from app.repositories.participant_repo import ParticipantRepo
from app.repositories.session_repo import SessionRepo
from app.repositories.ui_event_repo import UiEventRepo
from app.repositories.llm_call_repo import LLMCallRepo
from app.repositories.case_repo import CaseRepo
from app.services.analysis import (
    _dedupe_presentations_by_session_case,
    _action_matches_gold,
    ALL_ACTIONS,
    _percentile,
    _as_utc,
    _LOG_STATS_KEYS_SCALAR,
    _bucket_dt,
)
from app.db.models import CasePresentation
from app.schemas.common import ACTION_LABEL_ZH
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from datetime import datetime as dt, timedelta, timezone
from collections import defaultdict


class AnalysisService:
    """Stateless aggregation service."""

    @staticmethod
    async def session_formal_performance(session_repo, session_id: str) -> dict[str, Any]:
        # Delegate to existing implementation which uses raw SQLAlchemy;
        # kept for backward compatibility during the incremental refactor.
        from app.services.analysis import session_formal_performance as _fn
        return await _fn(session_repo._db, session_id)

    @staticmethod
    async def completion_stats(participant_repo: ParticipantRepo) -> dict[str, Any]:
        total = await participant_repo.count_total()
        completed = await participant_repo.count_completed()
        by_cond = await participant_repo.condition_counts()
        return {
            "totalParticipants": total,
            "completed": completed,
            "completionRate": completed / total if total else 0.0,
            "byCondition": [{"condition": c, "count": n} for c, n in by_cond],
        }

    @staticmethod
    async def llm_call_stats(llm_repo: LLMCallRepo) -> dict[str, Any]:
        rows = await llm_repo.all()
        now = dt.now(timezone.utc)
        cutoff = now - timedelta(hours=24)
        purposes: defaultdict[str, list] = defaultdict(list)
        for r in rows:
            purposes[r.purpose].append(r)
        per = []
        for purpose, group in purposes.items():
            lats = sorted(r.latency_ms or 0 for r in group)
            errs = sum(1 for r in group if r.error)
            per.append({
                "purpose": purpose, "count": len(group),
                "errorRate": errs / len(group) if group else 0.0,
                "p50Ms": _percentile(lats, 0.50),
                "p95Ms": _percentile(lats, 0.95),
                "promptTokens": sum(r.prompt_tokens or 0 for r in group),
                "completionTokens": sum(r.completion_tokens or 0 for r in group),
                "count24h": sum(1 for r in group if _as_utc(r.created_at) and _as_utc(r.created_at) >= cutoff),
            })
        per.sort(key=lambda x: x["purpose"])
        total_count = len(rows)
        total_errors = sum(1 for r in rows if r.error)
        return {
            "totals": {
                "count": total_count, "errors": total_errors,
                "errorRate": total_errors / total_count if total_count else 0.0,
                "promptTokens": sum(r.prompt_tokens or 0 for r in rows),
                "completionTokens": sum(r.completion_tokens or 0 for r in rows),
            },
            "perPurpose": per,
        }
