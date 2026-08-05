"""Concurrency / duplicate-submit regression tests.

These reproduce the failure modes a participant on a flaky mainland-China
mobile network actually hits:

  * the submit request stalls, the client's 25s timeout fires and shows
    "提交失败", the participant taps 提交 again — but the *first* request is
    still running server-side (aborting a fetch does not cancel the FastAPI
    handler), so two writes for the same case race each other;
  * the same for the post-survey submit, which is the very last step and the
    one that hands out the completion code;
  * double-tapping a button on a slow phone before React re-renders it into
    the disabled state.

Every one of these must end with the participant moving forward and exactly
one row in the database — never a 500 ("网络异常，请稍后重试").
"""

from __future__ import annotations

import asyncio
import time

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.models import Action, CasePresentation, Participant, PostSurvey
from app.db.session import get_session_factory
from app.schemas.post_survey_payload import post_survey_v7_all_threes
from app.scripts.seed import upsert_cases, upsert_order_templates


@pytest.fixture(autouse=True)
async def _seed():
    await upsert_cases()
    await upsert_order_templates()


async def _start_session(client: AsyncClient) -> dict:
    r = await client.post("/api/session")
    assert r.status_code == 200, r.text
    return r.json()


def _action_body(session_id: str, case_id: str, order_index: int) -> dict:
    now = int(time.time() * 1000)
    return {
        "sessionId": session_id,
        "caseId": case_id,
        "orderIndex": order_index,
        "isPractice": False,
        "selectedAction": "edit_then_send",
        "finalReplyText": "医生修改后的回复内容。",
        "caseActionReasonCode": "wording_issue",
        "quickSurvey": {"caseDecisionConfidence": 4, "caseDraftHelpfulness": 3},
        "timing": {"startedAt": now - 60_000, "endedAt": now, "durationMs": 60_000},
    }


async def _count(model, **filters) -> int:
    factory = get_session_factory()
    async with factory() as db:
        stmt = select(func.count()).select_from(model)
        for col, val in filters.items():
            stmt = stmt.where(getattr(model, col) == val)
        return int((await db.execute(stmt)).scalar_one())


@pytest.mark.asyncio
async def test_concurrent_duplicate_action_never_500s(client: AsyncClient) -> None:
    """Two in-flight submits for the same case must both succeed idempotently.

    This is the exact frontend sequence: the case page opens a presentation,
    then the participant submits twice. Both submits find the same in-progress
    presentation, and `actions.case_presentation_id` is UNIQUE — so without
    server-side serialization the loser raises IntegrityError → 500 → the
    participant sees "网络异常，请稍后重试" even though their answer was saved.
    """
    s = await _start_session(client)
    sid, cid = s["sessionId"], s["caseOrder"][0]
    ro = await client.post(
        "/api/case/open", json={"sessionId": sid, "caseId": cid, "orderIndex": 0}
    )
    assert ro.status_code == 200, ro.text

    body = _action_body(sid, cid, 0)
    r1, r2 = await asyncio.gather(
        client.post("/api/action", json=body),
        client.post("/api/action", json=body),
        return_exceptions=True,
    )

    for r in (r1, r2):
        assert not isinstance(r, BaseException), f"request raised: {r!r}"
        assert r.status_code == 200, f"duplicate submit returned {r.status_code}: {r.text}"

    assert r1.json()["casePresentationId"] == r2.json()["casePresentationId"]
    assert await _count(Action) == 1, "duplicate submit created a second action row"
    assert await _count(CasePresentation) == 1


@pytest.mark.asyncio
async def test_concurrent_action_without_open_stays_single(client: AsyncClient) -> None:
    """Same double-submit, but when /api/case/open never landed.

    The frontend treats /api/case/open as optional telemetry and renders the
    case even if it failed, so a participant on a flaky network can reach the
    submit step with no presentation row yet. Both submits would then create
    their own presentation *and* their own action — one case answered twice
    in the export, with no unique constraint to catch it.
    """
    s = await _start_session(client)
    sid, cid = s["sessionId"], s["caseOrder"][0]
    body = _action_body(sid, cid, 0)

    r1, r2 = await asyncio.gather(
        client.post("/api/action", json=body),
        client.post("/api/action", json=body),
        return_exceptions=True,
    )
    for r in (r1, r2):
        assert not isinstance(r, BaseException), f"request raised: {r!r}"
        assert r.status_code == 200, r.text

    assert await _count(Action) == 1
    assert await _count(CasePresentation) == 1


@pytest.mark.asyncio
async def test_concurrent_case_open_creates_one_presentation(client: AsyncClient) -> None:
    """React StrictMode / a quick back-forward fires /api/case/open twice.

    Both requests SELECT-then-INSERT, so without a guard the session ends up
    with two CasePresentation rows for one case — an extra empty row in the
    export and an ambiguous target for the later action.
    """
    s = await _start_session(client)
    sid, cid = s["sessionId"], s["caseOrder"][0]
    payload = {"sessionId": sid, "caseId": cid, "orderIndex": 0}

    results = await asyncio.gather(
        *(client.post("/api/case/open", json=payload) for _ in range(3)),
        return_exceptions=True,
    )
    for r in results:
        assert not isinstance(r, BaseException), f"request raised: {r!r}"
        assert r.status_code == 200, r.text

    assert await _count(CasePresentation) == 1, "case/open raced into duplicate rows"


@pytest.mark.asyncio
async def test_duplicate_post_survey_is_idempotent(client: AsyncClient) -> None:
    """The final submit must not write two post-survey rows for one session.

    A duplicate row silently doubles the participant in every export and makes
    "how many people finished" wrong.
    """
    s = await _start_session(client)
    body = {"sessionId": s["sessionId"], "payload": post_survey_v7_all_threes()}

    r1 = await client.post("/api/post-survey", json=body)
    assert r1.status_code == 200, r1.text
    r2 = await client.post("/api/post-survey", json=body)
    assert r2.status_code == 200, r2.text

    assert r1.json()["completionCode"] == r2.json()["completionCode"]
    assert await _count(PostSurvey) == 1, "post-survey submitted twice created two rows"


@pytest.mark.asyncio
async def test_concurrent_post_survey_is_idempotent(client: AsyncClient) -> None:
    """Same as above but genuinely simultaneous (timeout-then-retry case)."""
    s = await _start_session(client)
    body = {"sessionId": s["sessionId"], "payload": post_survey_v7_all_threes()}

    r1, r2 = await asyncio.gather(
        client.post("/api/post-survey", json=body),
        client.post("/api/post-survey", json=body),
        return_exceptions=True,
    )
    for r in (r1, r2):
        assert not isinstance(r, BaseException), f"request raised: {r!r}"
        assert r.status_code == 200, r.text

    assert await _count(PostSurvey) == 1


@pytest.mark.asyncio
async def test_many_sessions_start_concurrently(client: AsyncClient) -> None:
    """50 participants clicking 「开始」 at once all get their own session."""
    results = await asyncio.gather(
        *(client.post("/api/session") for _ in range(50)),
        return_exceptions=True,
    )
    ids = set()
    for r in results:
        assert not isinstance(r, BaseException), f"request raised: {r!r}"
        assert r.status_code == 200, r.text
        ids.add(r.json()["participantId"])

    assert len(ids) == 50
    assert await _count(Participant) == 50
