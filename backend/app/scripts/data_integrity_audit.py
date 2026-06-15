"""Data integrity audit for the Medical-AI database.

Runs cross-table integrity checks against the database and reports
[PASS] / [WARN] / [FAIL] for each check. Designed for CI integration.

Usage: python -m app.scripts.data_integrity_audit
"""

from __future__ import annotations

import asyncio
import sys

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Action,
    Case,
    CasePresentation,
    CaseSurvey,
    PostSurvey,
    Session,
    UiEvent,
)
from app.db.session import get_session_factory


# ---------------------------------------------------------------------------
# Result collector
# ---------------------------------------------------------------------------


class AuditResult:
    """Collects [PASS] / [WARN] / [FAIL] outcomes."""

    def __init__(self) -> None:
        self.passes: list[str] = []
        self.warnings: list[str] = []
        self.fails: list[str] = []

    def pass_(self, msg: str) -> None:
        self.passes.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def fail(self, msg: str) -> None:
        self.fails.append(msg)

    @property
    def has_fail(self) -> bool:
        return bool(self.fails)

    def print_report(self) -> None:
        for msg in self.passes:
            print(f"  [PASS] {msg}")
        for msg in self.warnings:
            print(f"  [WARN] {msg}")
        for msg in self.fails:
            print(f"  [FAIL] {msg}")

    def summary(self) -> str:
        parts: list[str] = []
        if self.passes:
            parts.append(f"{len(self.passes)} passed")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warnings")
        if self.fails:
            parts.append(f"{len(self.fails)} failures")
        return ", ".join(parts) if parts else "no checks ran"


# ---------------------------------------------------------------------------
# Individual audit checks
# ---------------------------------------------------------------------------


async def check_completed_session_actions(
    db: AsyncSession,
    result: AuditResult,
) -> None:
    """Check 1: Each completed session has exactly 8 actions (one per formal case)."""
    sessions = (
        await db.execute(
            select(Session)
            .where(Session.status == "completed")
            .options(
                selectinload(Session.presentations)
                .selectinload(CasePresentation.action),
                selectinload(Session.presentations)
                .selectinload(CasePresentation.case),
            )
        )
    ).scalars().all()

    bad: list[str] = []
    for s in sessions:
        formal = [p for p in s.presentations if p.case is not None and not p.case.is_practice]
        n = sum(1 for p in formal if p.action is not None)
        if n != 8:
            bad.append(f"{s.id[:8]} ({n})")

    if bad:
        result.fail(
            f"{len(bad)} completed sessions without 8 actions: "
            f"{'; '.join(bad[:5])}{'...' if len(bad) > 5 else ''}",
        )
    else:
        result.pass_(f"all {len(sessions)} completed sessions have 8 actions")


async def check_attention_check(
    db: AsyncSession,
    result: AuditResult,
) -> None:
    """Check 2: PostSurvey payload contains attn_post_1 == 4."""
    surveys = (await db.execute(select(PostSurvey))).scalars().all()

    missing: list[str] = []
    wrong: list[str] = []
    for s in surveys:
        payload = s.payload or {}
        val = payload.get("attn_post_1")
        if val is None:
            missing.append(s.id[:8])
        elif val != 4:
            wrong.append(f"{s.id[:8]} (got {val})")

    total = len(surveys)
    if total == 0:
        result.warn("no post_surveys found to check attention")
        return

    if missing:
        result.warn(
            f"{len(missing)} post_surveys missing attn_post_1 field: "
            f"{'; '.join(missing[:5])}",
        )
    if wrong:
        result.warn(
            f"{len(wrong)} post_surveys have wrong attn_post_1 value (expected 4): "
            f"{'; '.join(wrong[:5])}",
        )
    if not missing and not wrong:
        result.pass_(f"all {total} post_surveys have attn_post_1 == 4")


async def check_session_start_event(
    db: AsyncSession,
    result: AuditResult,
) -> None:
    """Check 3: Each session has at least one session_started ui_event."""
    session_ids = list((await db.execute(select(Session.id))).scalars().all())
    if not session_ids:
        result.warn("no sessions found to check start events")
        return

    event_rows = (
        await db.execute(
            select(UiEvent.session_id).where(
                UiEvent.event_type == "session_started",
                UiEvent.session_id.in_(session_ids),
            )
        )
    ).scalars().all()

    sessions_with_event = set(event_rows)
    missing = [sid for sid in session_ids if sid not in sessions_with_event]

    if missing:
        result.fail(
            f"{len(missing)} sessions missing session_started event: "
            f"{'; '.join(s[:8] for s in missing[:5])}"
            f"{'...' if len(missing) > 5 else ''}",
        )
    else:
        result.pass_(
            f"all {len(session_ids)} sessions have a session_started event",
        )


async def check_orphan_actions(
    db: AsyncSession,
    result: AuditResult,
) -> None:
    """Check 4: No orphan Actions (every case_presentation_id must exist in case_presentations)."""
    cp_ids = set((await db.execute(select(CasePresentation.id))).scalars().all())
    action_cp_ids = set(
        (await db.execute(select(Action.case_presentation_id))).scalars().all(),
    )

    orphan = action_cp_ids - cp_ids
    if orphan:
        result.fail(
            f"{len(orphan)} orphan Action records referencing non-existent "
            f"case_presentation: {'; '.join(list(orphan)[:5])}",
        )
    else:
        result.pass_(
            f"all {len(action_cp_ids)} Action records reference valid case_presentations",
        )


async def check_orphan_case_presentations(
    db: AsyncSession,
    result: AuditResult,
) -> None:
    """Check 5: No orphan CasePresentations (session_id and case_id must exist)."""
    cp_rows = (await db.execute(select(CasePresentation))).scalars().all()
    session_ids = set((await db.execute(select(Session.id))).scalars().all())
    case_ids = set((await db.execute(select(Case.id))).scalars().all())

    bad_sessions: list[str] = []
    bad_cases: list[str] = []
    for cp in cp_rows:
        if cp.session_id not in session_ids:
            bad_sessions.append(cp.id[:8])
        if cp.case_id not in case_ids:
            bad_cases.append(cp.id[:8])

    if bad_sessions:
        result.fail(
            f"{len(bad_sessions)} CasePresentations reference non-existent sessions",
        )
    if bad_cases:
        result.fail(
            f"{len(bad_cases)} CasePresentations reference non-existent cases",
        )
    if not bad_sessions and not bad_cases:
        result.pass_(
            f"all {len(cp_rows)} CasePresentation records have valid session_id and case_id",
        )


async def check_orphan_case_surveys(
    db: AsyncSession,
    result: AuditResult,
) -> None:
    """Check 6: No orphan CaseSurveys (case_presentation_id must exist)."""
    cp_ids = set((await db.execute(select(CasePresentation.id))).scalars().all())
    survey_cp_ids = set(
        (await db.execute(select(CaseSurvey.case_presentation_id))).scalars().all(),
    )

    orphan = survey_cp_ids - cp_ids
    if orphan:
        result.fail(f"{len(orphan)} orphan CaseSurvey records")
    else:
        result.pass_(
            f"all {len(survey_cp_ids)} CaseSurvey records reference valid "
            f"case_presentations",
        )


async def check_orphan_ui_events(
    db: AsyncSession,
    result: AuditResult,
) -> None:
    """Check 7: No orphan UiEvents (session_id must exist; case_presentation_id is nullable)."""
    session_ids = set((await db.execute(select(Session.id))).scalars().all())
    ui_session_ids = set(
        (await db.execute(select(UiEvent.session_id))).scalars().all(),
    )

    orphan = ui_session_ids - session_ids
    if orphan:
        result.fail(
            f"{len(orphan)} orphan UiEvent records reference non-existent sessions",
        )
    else:
        total = await db.scalar(select(func.count(UiEvent.id)))
        result.pass_(f"all {total} UiEvent records have valid session_id")


async def check_gold_action_distribution(
    db: AsyncSession,
    result: AuditResult,
) -> None:
    """Check 9: Gold action distribution in completed sessions approximates 1/3/3/1.

    Expected distribution:
    - send_as_is:       1 per 8 actions
    - edit_then_send:   3 per 8 actions
    - discard_and_rewrite: 3 per 8 actions
    - escalate:         1 per 8 actions
    """
    rows = (
        await db.execute(
            select(Action.selected_action)
            .join(CasePresentation, Action.case_presentation_id == CasePresentation.id)
            .join(Session, CasePresentation.session_id == Session.id)
            .where(Session.status == "completed"),
        )
    ).scalars().all()

    if not rows:
        result.warn("no actions in completed sessions to check gold distribution")
        return

    counter = Counter(rows)
    total = len(rows)

    expected_counts = {
        "send_as_is": total // 8,
        "edit_then_send": 3 * total // 8,
        "discard_and_rewrite": 3 * total // 8,
        "escalate": total // 8,
    }

    deviations: list[str] = []
    for action_name, expected in expected_counts.items():
        actual = counter.get(action_name, 0)
        diff = abs(actual - expected)
        tolerance = max(2, expected // 5)  # allow 20% deviation, min 2
        if diff > tolerance:
            deviations.append(
                f"{action_name}: got {actual}, expected ~{expected}",
            )

    if deviations:
        result.warn(
            f"gold action distribution deviates from 1/3/3/1: "
            f"{'; '.join(deviations)}",
        )
    else:
        result.pass_(
            f"gold action distribution matches 1/3/3/1 pattern "
            f"(n={total}): {dict(counter)}",
        )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def run_audit() -> int:
    result = AuditResult()
    factory = get_session_factory()

    print("Running data integrity audit...")
    print()

    async with factory() as db:
        print("  [1/9] Completed session action count...")
        await check_completed_session_actions(db, result)

        print("  [2/9] Attention check...")
        await check_attention_check(db, result)

        print("  [3/9] Session start event check...")
        await check_session_start_event(db, result)

        print("  [4/9] Orphan action check...")
        await check_orphan_actions(db, result)

        print("  [5/9] Orphan case presentation check...")
        await check_orphan_case_presentations(db, result)

        print("  [6/9] Orphan case survey check...")
        await check_orphan_case_surveys(db, result)

        print("  [7/9] Orphan UI event check...")
        await check_orphan_ui_events(db, result)

        print("  [8/9] Gold action distribution check...")
        await check_gold_action_distribution(db, result)

    print()
    print("--- Audit results ---")
    result.print_report()
    print()
    print(f"Summary: {result.summary()}")

    return 1 if result.has_fail else 0


def main() -> int:
    return asyncio.run(run_audit())


if __name__ == "__main__":
    sys.exit(main())
