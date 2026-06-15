"""Test anonymised export mode strips PII from actions and participants tables."""

from __future__ import annotations

import csv
import io
import json

import pytest
from httpx import AsyncClient

from app.db.session import get_session_factory
from app.scripts.seed import upsert_cases, upsert_order_templates


@pytest.fixture(autouse=True)
async def _seed():
    await upsert_cases()
    await upsert_order_templates()


@pytest.mark.asyncio
async def test_export_actions_anonymized_removes_reply_text(
    admin_token: str, client: AsyncClient
) -> None:
    # Create one participant/session and an action; then export actions
    # with anonymised=true and verify the reply text fields are not present.
    s = (await client.post("/api/session")).json()
    sid = s["sessionId"]
    cid = s["caseOrder"][0]

    # Open case + submit action
    op = await client.post(
        "/api/case/open", json={"sessionId": sid, "caseId": cid, "orderIndex": 0}
    )
    pres_id = op.json()["casePresentationId"]

    await client.post(
        "/api/action",
        json={
            "sessionId": sid,
            "caseId": cid,
            "orderIndex": 0,
            "selectedAction": "send_as_is",
            "finalReplyText": "sensitive reply containing medical advice",
            "quickSurvey": {
                "caseDecisionConfidence": 3,
                "caseDraftHelpfulness": 4,
            },
            "caseActionReasonCode": "basically_ok",
            "caseActionReasonText": "looks fine",
            "escalateSubtype": "urgent_evaluation",
            "escalateReason": "patient may be at risk",
            "timing": {
                "startedAt": 1_000_000_000_000,
                "endedAt": 1_000_000_005_000,
                "durationMs": 5000,
            },
        },
    )

    # Anonymised export
    r = await client.get(
        "/api/admin/export",
        params={"table": "actions", "format": "csv", "anonymized": "true"},
        headers={"X-Admin-Token": admin_token},
    )
    assert r.status_code == 200
    reader = csv.DictReader(io.StringIO(r.text))
    rows = list(reader)
    assert len(rows) >= 1

    # The anonymised CSV must NOT contain the real text
    for row in rows:
        # final_reply_text and escalate_reason should be null/empty when anonymized
        assert (
            row["final_reply_text"] == "" or row["final_reply_text"] is None
        ), f"anonymized export leaked final_reply_text: {row['final_reply_text'][:40]}"
        assert (
            row["escalate_reason"] == "" or row["escalate_reason"] is None
        ), f"anonymized export leaked escalate_reason: {row['escalate_reason'][:40]}"


@pytest.mark.asyncio
async def test_export_participants_anonymized_hashes_ids(
    admin_token: str, client: AsyncClient
) -> None:
    # Create one completed participant flow
    from app.schemas.post_survey_payload import post_survey_v7_all_threes

    s = (await client.post("/api/session")).json()
    sid = s["sessionId"]

    await client.post(
        "/api/pre-survey",
        json={
            "sessionId": sid,
            "answers": {
                "pre_specialty": "皮肤科",
                "pre_training_level": "住院医师",
                "pre_years_post_residency": 2,
                "pre_weekly_msg_volume": "1—10 条",
                "pre_ai_drafting_familiarity": 3,
            },
        },
    )

    for i, cid in enumerate(s["caseOrder"]):
        await client.post("/api/case/open", json={
            "sessionId": sid, "caseId": cid, "orderIndex": i,
        })
        await client.post(
            "/api/action",
            json={
                "sessionId": sid,
                "caseId": cid,
                "orderIndex": i,
                "selectedAction": "send_as_is",
                "finalReplyText": "ok",
                "quickSurvey": {"caseDecisionConfidence": 3, "caseDraftHelpfulness": 3},
                "caseActionReasonCode": "basically_ok",
                "timing": {
                    "startedAt": 1_000_000_000_000,
                    "endedAt": 1_000_000_000_000,
                    "durationMs": 0,
                },
            },
        )

    await client.post(
        "/api/post-survey",
        json={"sessionId": sid, "payload": post_survey_v7_all_threes()},
    )

    # Regular export — participant_id is real
    r_reg = await client.get(
        "/api/admin/export",
        params={"table": "participants", "format": "csv", "anonymized": "false"},
        headers={"X-Admin-Token": admin_token},
    )
    reader = csv.DictReader(io.StringIO(r_reg.text))
    reg = [r for r in reader if r["completed_flag"] in ("true", "True", "1")]
    assert len(reg) == 1
    real_id = reg[0]["participant_id"]

    # Anonymised export — participant_id must differ from real
    r_anon = await client.get(
        "/api/admin/export",
        params={"table": "participants", "format": "csv", "anonymized": "true"},
        headers={"X-Admin-Token": admin_token},
    )
    reader = csv.DictReader(io.StringIO(r_anon.text))
    anon = [r for r in reader if r["completed_flag"] in ("true", "True", "1")]
    assert len(anon) == 1
    assert anon[0]["participant_id"] != real_id, (
        "anonymized export must hash participant_id"
    )
    # Anonymised ID is 16 hex chars
    assert len(anon[0]["participant_id"]) == 16

    # completion_code should also be anonymized if completed_flag=true
    assert anon[0]["completion_code"].startswith("AIDR-")
    assert anon[0]["completion_code"] != reg[0]["completion_code"]


@pytest.mark.asyncio
async def test_export_anonymized_is_deterministic(
    admin_token: str, client: AsyncClient
) -> None:
    """Same participant exported twice with anonymised=true must produce
    the same anonymised ID so researchers can join tables."""
    s = (await client.post("/api/session")).json()

    r1 = await client.get(
        "/api/admin/export",
        params={"table": "participants", "format": "csv", "anonymized": "true"},
        headers={"X-Admin-Token": admin_token},
    )
    r2 = await client.get(
        "/api/admin/export",
        params={"table": "participants", "format": "csv", "anonymized": "true"},
        headers={"X-Admin-Token": admin_token},
    )
    rows1 = list(csv.DictReader(io.StringIO(r1.text)))
    rows2 = list(csv.DictReader(io.StringIO(r2.text)))

    assert rows1[0]["participant_id"] == rows2[0]["participant_id"]
