from __future__ import annotations

import time

import pytest
from httpx import AsyncClient

from app.scripts.seed import upsert_cases, upsert_order_templates


@pytest.fixture(autouse=True)
async def _seed():
    await upsert_cases()
    await upsert_order_templates()


async def _start_session(client: AsyncClient) -> dict:
    r = await client.post("/api/session")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_session_creates_with_random_condition_and_template(client: AsyncClient) -> None:
    s = await _start_session(client)
    assert s["sessionId"]
    assert s["participantId"]
    assert s["condition"] in ("plain", "guardrail")
    assert 1 <= s["orderTemplateId"] <= 4
    assert len(s["caseOrder"]) == 8
    assert s["practiceCaseId"] == "case_practice"


@pytest.mark.asyncio
async def test_case_endpoint_filters_by_condition(client: AsyncClient) -> None:
    # repeatedly create until we see both conditions, then assert each
    seen_conditions = {}
    for _ in range(20):
        s = await _start_session(client)
        if s["condition"] not in seen_conditions:
            seen_conditions[s["condition"]] = s
        if len(seen_conditions) == 2:
            break
    assert "plain" in seen_conditions and "guardrail" in seen_conditions

    plain = seen_conditions["plain"]
    rp = await client.get(f"/api/case/case_01?sessionId={plain['sessionId']}")
    assert rp.status_code == 200
    assert rp.json()["case"].get("guardrail") is None

    guard = seen_conditions["guardrail"]
    rg = await client.get(f"/api/case/case_01?sessionId={guard['sessionId']}")
    assert rg.status_code == 200
    g_case = rg.json()["case"]
    assert g_case["guardrail"] is not None
    assert len(g_case["guardrail"]["factsUsed"]) >= 1
    assert "checklist" in g_case["guardrail"]


@pytest.mark.asyncio
async def test_full_participant_flow(client: AsyncClient) -> None:
    s = await _start_session(client)
    sid = s["sessionId"]

    # pre-survey
    r = await client.post(
        "/api/pre-survey",
        json={
            "sessionId": sid,
            "answers": {
                "specialty": "心血管内科",
                "training_level": "主治医师",
                "years_practice": 6,
                "weekly_message_volume": "11—25 条",
                "prior_ai_use": "每周使用",
                "ai_familiarity": 5,
                "ai_brands_used": ["DeepSeek", "文心一言"],
            },
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    now = int(time.time() * 1000)

    # walk through all 8 cases by gold action (mock heuristic: ALL send_as_is for simplicity here)
    for i, cid in enumerate(s["caseOrder"]):
        # fetch case
        cr = await client.get(f"/api/case/{cid}?sessionId={sid}")
        assert cr.status_code == 200
        case_payload = cr.json()["case"]

        # submit action
        ar = await client.post(
            "/api/action",
            json={
                "sessionId": sid,
                "caseId": cid,
                "orderIndex": i,
                "isPractice": False,
                "selectedAction": "send_as_is",
                "finalReplyText": case_payload["aiDraft"],
                "quickSurvey": {"item1": 5, "item2": 5, "item3": 5},
                "timing": {
                    "startedAt": now - 5000,
                    "endedAt": now,
                    "durationMs": 5000,
                },
                "clientStats": {
                    "timeToFirstClickMs": 800,
                    "panelClickCounts": {"ai_draft_panel": 1},
                    "checklistChecked": [True, True, True],
                    "checklistToggleCount": 3,
                    "editKeystrokes": 0,
                    "editBoxOpenedCount": 0,
                    "pageBlurCount": 0,
                    "pageFocusCount": 0,
                    "visibilityHiddenMs": 0,
                },
            },
        )
        assert ar.status_code == 200, ar.text
        body = ar.json()
        assert body["ok"] is True
        # final_reply_text == ai_draft → editDistance == 0
        assert body["editDistance"] == 0

    # post-survey
    pr = await client.post(
        "/api/post-survey",
        json={
            "sessionId": sid,
            "payload": {
                "trust_1": 5, "trust_2": 4, "trust_3": 5,
                "transparency_1": 4, "transparency_2": 4, "transparency_3": 4,
                "workflow_1": 5, "workflow_2": 5, "workflow_3": 3,
                "accountability_1": 7, "accountability_2": 6, "accountability_3": 5,
                "overreliance_1": 5, "overreliance_2": 4, "overreliance_3": 5,
                "open_1": "希望增加风险提示折叠展开记录",
                "open_2": "界面流畅",
            },
        },
    )
    assert pr.status_code == 200
    body = pr.json()
    assert body["ok"] is True
    assert body["completionCode"].startswith("AIDR-")


@pytest.mark.asyncio
async def test_action_validates_action_enum(client: AsyncClient) -> None:
    s = await _start_session(client)
    now = int(time.time() * 1000)
    r = await client.post(
        "/api/action",
        json={
            "sessionId": s["sessionId"],
            "caseId": "case_01",
            "orderIndex": 0,
            "selectedAction": "invalid_action",
            "finalReplyText": "x",
            "quickSurvey": {"item1": 5, "item2": 5, "item3": 5},
            "timing": {"startedAt": now - 1000, "endedAt": now, "durationMs": 1000},
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_ui_event_endpoint_is_lenient(client: AsyncClient) -> None:
    s = await _start_session(client)
    r = await client.post(
        "/api/ui-event",
        json={
            "sessionId": s["sessionId"],
            "eventType": "panel_clicked",
            "payload": {"panel": "facts_panel"},
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


@pytest.mark.asyncio
async def test_admin_endpoints_require_token(client: AsyncClient) -> None:
    r1 = await client.get("/api/admin/summary")
    assert r1.status_code == 401
    r2 = await client.get("/api/admin/export?table=actions&format=csv")
    assert r2.status_code == 401


@pytest.mark.asyncio
async def test_admin_summary_with_data(client: AsyncClient, admin_token: str) -> None:
    # Create 3 participants with known behavior for confusion matrix sanity.
    sessions = [await _start_session(client) for _ in range(3)]
    now = int(time.time() * 1000)

    # gold-picker cheats: read seed JSON to know gold action
    from app.scripts.data_loader import load_cases

    gold_by_id = {c["id"]: c["goldAction"] for c in load_cases()}

    # 2 participants always pick gold; 1 always picks send_as_is
    pickers = [lambda c: gold_by_id[c], lambda c: gold_by_id[c], lambda _c: "send_as_is"]

    for s, picker in zip(sessions, pickers):
        for i, cid in enumerate(s["caseOrder"]):
            ar = await client.post(
                "/api/action",
                json={
                    "sessionId": s["sessionId"],
                    "caseId": cid,
                    "orderIndex": i,
                    "selectedAction": picker(cid),
                    "finalReplyText": "test",
                    "quickSurvey": {"item1": 5, "item2": 5, "item3": 5},
                    "timing": {"startedAt": now - 5000, "endedAt": now, "durationMs": 5000},
                },
            )
            assert ar.status_code == 200, ar.text
        await client.post(
            "/api/post-survey",
            json={"sessionId": s["sessionId"], "payload": {"trust_1": 5}},
        )

    rs = await client.get(
        "/api/admin/summary",
        headers={"X-Admin-Token": admin_token},
    )
    assert rs.status_code == 200
    body = rs.json()
    assert body["completion"]["completed"] == 3
    cm = body["confusionMatrix"]
    assert cm["total"] == 24  # 3 × 8 formal cases
    # 2 perfect (16/16) + 1 lazy who matches at gold=send_as_is cases (some) → > 50%
    assert 0.5 <= cm["accuracy"] < 1.0
    assert cm["actionsZh"] == ["直接发送", "编辑后发送", "弃用并重写", "升级处理"]
    assert len(body["perCase"]) == 8
    assert len(body["perParticipant"]) == 3


@pytest.mark.asyncio
async def test_admin_export_csv_actions(client: AsyncClient, admin_token: str) -> None:
    s = await _start_session(client)
    now = int(time.time() * 1000)
    await client.post(
        "/api/action",
        json={
            "sessionId": s["sessionId"],
            "caseId": "case_practice",
            "orderIndex": -1,
            "isPractice": True,
            "selectedAction": "edit_then_send",
            "finalReplyText": "已修改的中文回复",
            "quickSurvey": {"item1": 5, "item2": 5, "item3": 5},
            "timing": {"startedAt": now - 3000, "endedAt": now, "durationMs": 3000},
        },
    )

    r = await client.get(
        "/api/admin/export",
        params={"table": "actions", "format": "csv"},
        headers={"X-Admin-Token": admin_token},
    )
    assert r.status_code == 200
    text = r.text
    assert "actionId" in text and "finalReplyText" in text
    assert "已修改的中文回复" in text
    assert "editDistance" in text
    assert "goldActionMatch" in text


@pytest.mark.asyncio
async def test_admin_export_summary_csv_includes_chinese_labels(
    client: AsyncClient, admin_token: str
) -> None:
    r = await client.get(
        "/api/admin/export",
        params={"table": "summary", "format": "csv"},
        headers={"X-Admin-Token": admin_token},
    )
    assert r.status_code == 200
    # summary CSV may be empty rows but the header must exist
    assert "kind" in r.text.splitlines()[0]
