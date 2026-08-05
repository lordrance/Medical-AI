"""Serialize the concurrent writes that belong to a single participant.

Why this exists
---------------
Every participant-side write endpoint follows a SELECT-then-INSERT shape
("does a row for this case already exist? no → create it"). That is a
textbook race, and it fires in production for a very ordinary reason:

  the participant submits, their phone's connection stalls, the frontend's
  25s timeout gives up and shows "提交失败", they tap 提交 again — but the
  first request is still running on the server (aborting a `fetch` does not
  cancel the FastAPI handler). Now two identical writes run at once.

Observed consequences before this guard existed:

  * ``/api/action``  — both requests found the same in-progress
    CasePresentation and both inserted an Action for it. ``actions``
    .case_presentation_id is UNIQUE, so the loser raised IntegrityError →
    HTTP 500 → the participant saw "网络异常，请稍后重试" even though their
    answer had been saved.
  * ``/api/case/open`` — both requests created their own CasePresentation.
    The production database had accumulated 23 such duplicate rows.
  * ``/api/post-survey`` — two post_survey rows for one session, which
    double-counts that participant in every export.

The lock is keyed by session id, so it only ever serializes one person's
own requests; two different participants never contend. That keeps it free
at 100 concurrent users while closing all three races with one mechanism.

Postgres uses a transaction-scoped advisory lock, which is held across
gunicorn workers (the race is cross-worker — requests round-robin) and is
released automatically on commit or rollback. SQLite (tests / local dev)
has no such primitive and runs single-process, so an in-process asyncio
lock is exactly equivalent there.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Only used on the SQLite path (single process, bounded by the number of
# sessions a test run creates), so unbounded growth is not a concern.
_local_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


@asynccontextmanager
async def session_write_lock(db: AsyncSession, session_id: str) -> AsyncIterator[None]:
    """Hold a per-session write lock for the duration of the block.

    Must wrap the *whole* handler body, commit included: releasing before the
    commit would reopen the very window this closes.
    """
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        # hashtext() maps the session id to the int the advisory-lock API
        # takes. A collision would merely make two unrelated participants
        # take turns for a few milliseconds, never a correctness problem.
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key)::bigint)"),
            {"key": session_id},
        )
        yield
        return

    async with _local_locks[session_id]:
        yield
