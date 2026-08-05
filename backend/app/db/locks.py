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
#
# 中文：只在 SQLite（本地开发 / 测试）路径上用。测试是单进程的，
# 一次跑下来最多几十个 session，所以这个字典无限增长也无所谓。
_local_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


@asynccontextmanager
async def session_write_lock(db: AsyncSession, session_id: str) -> AsyncIterator[None]:
    """Hold a per-session write lock for the duration of the block.

    Must wrap the *whole* handler body, commit included: releasing before the
    commit would reopen the very window this closes.

    中文：给「同一个人」的写请求排队。用法：

        async with session_write_lock(db, session.id):
            ...查、写、commit 全都要放在里面...

    ★ 必须把 commit 也包进来。如果提前放锁，第二个请求就会在第一个
    还没提交时进来，照样查不到数据、照样重复写——等于白加。
    """
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        # hashtext() maps the session id to the int the advisory-lock API
        # takes. A collision would merely make two unrelated participants
        # take turns for a few milliseconds, never a correctness problem.
        #
        # 中文：生产环境（Postgres）用「事务级咨询锁」。
        # - 它由数据库统一管理，所以 4 个 gunicorn 进程之间都有效
        #   （同一个人的两个请求很可能被分到不同进程，进程内的锁挡不住）。
        # - 「事务级」意味着 commit 或 rollback 时自动释放，
        #   不会因为代码漏写解锁而永久卡死。
        # - hashtext 把 session id 转成锁 API 要的整数。极小概率两个不同的
        #   session 算出同一个数，后果也只是两个陌生人排队几毫秒，不影响正确性。
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key)::bigint)"),
            {"key": session_id},
        )
        yield  # ← 调用方的代码在这里执行
        return

    # SQLite 没有咨询锁，但它本来就是单进程跑的，
    # 用 Python 自带的 asyncio 锁效果完全等价。
    async with _local_locks[session_id]:
        yield
