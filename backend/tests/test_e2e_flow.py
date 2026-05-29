from __future__ import annotations

import time

import pytest
from httpx import AsyncClient

from app.schemas.post_survey_payload import post_survey_v7_all_threes
from app.scripts.seed import upsert_cases, upsert_order_templates


def _action_v7_extras() -> dict:
    return {
        "quickSurvey": {"caseDecisionConfidence": 4, "caseDraftHelpfulness": 4},
        "caseActionReasonCode": "basically_ok",
    }


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
    p_case = rp.json()["case"]
    assert p_case.get("guardrail") is None

    guard = seen_conditions["guardrail"]
    rg = await client.get(f"/api/case/case_01?sessionId={guard['sessionId']}")
    assert rg.status_code == 200
    g_case = rg.json()["case"]
    assert g_case["guardrail"] is not None
    assert "checklist" in g_case["guardrail"]


@pytest.mark.asyncio
async def test_case_open_reuses_row_then_action_attaches(client: AsyncClient) -> None:
    s = await _start_session(client)
    sid = s["sessionId"]
    cid = s["caseOrder"][0]
    ro = await client.post(
        "/api/case/open",
        json={"sessionId": sid, "caseId": cid, "orderIndex": 0},
    )
    assert ro.status_code == 200
    pres_id = ro.json()["casePresentationId"]
    ro2 = await client.post(
        "/api/case/open",
        json={"sessionId": sid, "caseId": cid, "orderIndex": 0},
    )
    assert ro2.json()["casePresentationId"] == pres_id

    now = int(time.time() * 1000)
    from app.scripts.data_loader import load_cases

    draft = next(c for c in load_cases() if c["id"] == cid)["aiDraft"]
    ar = await client.post(
        "/api/action",
        json={
            "sessionId": sid,
            "caseId": cid,
            "orderIndex": 0,
            "selectedAction": "send_as_is",
            "finalReplyText": draft,
            **_action_v7_extras(),
            "timing": {"startedAt": now - 1000, "endedAt": now, "durationMs": 1000},
            "clientStats": {
                "interactionMetrics": {
                    "chartExpandToggleCount": 1,
                    "guardrailExpandToggleCount": 0,
                    "draftSourceSwitchCount": 2,
                    "chartEverExpandedToView": True,
                    "guardrailEverExpandedToView": False,
                    "sendAsIsAcknowledged": True,
                },
            },
        },
    )
    assert ar.status_code == 200
    assert ar.json()["casePresentationId"] == pres_id


@pytest.mark.asyncio
async def test_defect_case_returns_seeded_flawed_draft(client: AsyncClient) -> None:
    """defect_present cases must keep seeded flawed aiDraft; LLM must not 'fix' them."""
    from app.scripts.data_loader import load_cases

    # case_06 is the V3 single-escalation case with defectPresent=true
    # (GI bleed risk masked as 'observe with antacid').
    seeded = next(c for c in load_cases() if c["id"] == "case_06")
    assert seeded["defectPresent"] is True
    needle = seeded["aiDraft"][:24]

    s = await _start_session(client)
    r = await client.get(f"/api/case/case_06?sessionId={s['sessionId']}")
    assert r.status_code == 200
    draft = r.json()["case"]["aiDraft"]
    assert needle in draft


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
                "pre_specialty": "心血管内科",
                "pre_training_level": "主治医师",
                "pre_years_post_residency": 6,
                "pre_weekly_msg_volume": "11—25 条",
                "pre_ai_drafting_familiarity": 5,
            },
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    now = int(time.time() * 1000)

    from app.scripts.data_loader import load_cases

    gold_by_id = {c["id"]: c["goldAction"] for c in load_cases()}

    for i, cid in enumerate(s["caseOrder"]):
        cr = await client.get(f"/api/case/{cid}?sessionId={sid}")
        assert cr.status_code == 200
        case_payload = cr.json()["case"]
        ga = gold_by_id[cid]
        sel = ga
        if ga == "send_as_is":
            final_txt = case_payload["aiDraft"]
        elif ga == "escalate":
            final_txt = "[escalated]"
        elif ga == "edit_then_send":
            final_txt = case_payload["aiDraft"] + " 已审阅。"
        elif ga == "discard_and_rewrite":
            final_txt = "重写后的安全回复（测试）。"
        else:
            final_txt = case_payload["aiDraft"]

        body_json: dict = {
            "sessionId": sid,
            "caseId": cid,
            "orderIndex": i,
            "isPractice": False,
            "selectedAction": sel,
            "finalReplyText": final_txt,
            **_action_v7_extras(),
            "timing": {
                "startedAt": now - 5000,
                "endedAt": now,
                "durationMs": 5000,
            },
            "clientStats": {
                "timeToFirstClickMs": 800,
                "panelClickCounts": {"ai_draft_panel": 1},
                "checklistChecked": [],
                "checklistToggleCount": 0,
                "editKeystrokes": 0,
                "editBoxOpenedCount": 0,
                "pageBlurCount": 0,
                "pageFocusCount": 0,
                "visibilityHiddenMs": 0,
            },
        }
        if sel == "escalate":
            body_json["escalateSubtype"] = "urgent_evaluation"
            body_json["escalateReason"] = "测试：存在高风险需升级。"

        ar = await client.post("/api/action", json=body_json)
        assert ar.status_code == 200, ar.text
        body = ar.json()
        assert body["ok"] is True
        if sel == "send_as_is":
            assert body["editDistance"] == 0

    # post-survey
    pr = await client.post(
        "/api/post-survey",
        json={
            "sessionId": sid,
            "payload": post_survey_v7_all_threes(),
        },
    )
    assert pr.status_code == 200
    body = pr.json()
    assert body["ok"] is True
    assert body["completionCode"].startswith("AIDR-")
    perf = body.get("performance") or {}
    assert perf.get("total") == 8
    assert perf.get("correct") == 8
    assert perf.get("accuracy") == 1.0


@pytest.mark.asyncio
async def test_submit_same_case_twice_is_idempotent(client: AsyncClient) -> None:
    s = await _start_session(client)
    sid = s["sessionId"]
    cid = s["caseOrder"][0]
    now = int(time.time() * 1000)
    common = {
        "sessionId": sid,
        "caseId": cid,
        "orderIndex": 0,
        "selectedAction": "send_as_is",
        "finalReplyText": "same",
        **_action_v7_extras(),
        "timing": {"startedAt": now - 5000, "endedAt": now, "durationMs": 5000},
    }
    r1 = await client.post("/api/action", json=common)
    r2 = await client.post("/api/action", json=common)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["casePresentationId"] == r2.json()["casePresentationId"]


@pytest.mark.asyncio
async def test_escalate_requires_reason(client: AsyncClient) -> None:
    s = await _start_session(client)
    now = int(time.time() * 1000)
    r = await client.post(
        "/api/action",
        json={
            "sessionId": s["sessionId"],
            "caseId": "case_01",
            "orderIndex": 0,
            "selectedAction": "escalate",
            "finalReplyText": "[escalated]",
            "escalateSubtype": "urgent_evaluation",
            **_action_v7_extras(),
            "timing": {"startedAt": now - 1000, "endedAt": now, "durationMs": 1000},
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_quick_survey_max_five(client: AsyncClient) -> None:
    s = await _start_session(client)
    now = int(time.time() * 1000)
    r = await client.post(
        "/api/action",
        json={
            "sessionId": s["sessionId"],
            "caseId": "case_01",
            "orderIndex": 0,
            "selectedAction": "send_as_is",
            "finalReplyText": "x",
            "quickSurvey": {"caseDecisionConfidence": 6, "caseDraftHelpfulness": 3},
            "caseActionReasonCode": "basically_ok",
            "timing": {"startedAt": now - 1000, "endedAt": now, "durationMs": 1000},
        },
    )
    assert r.status_code == 422


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
            **_action_v7_extras(),
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

    for s, picker in zip(sessions, pickers, strict=True):
        for i, cid in enumerate(s["caseOrder"]):
            sel = picker(cid)
            payload: dict = {
                "sessionId": s["sessionId"],
                "caseId": cid,
                "orderIndex": i,
                "selectedAction": sel,
                "finalReplyText": "test",
                **_action_v7_extras(),
                "timing": {"startedAt": now - 5000, "endedAt": now, "durationMs": 5000},
            }
            if sel == "escalate":
                payload["escalateSubtype"] = "urgent_evaluation"
                payload["escalateReason"] = "单元测试升级说明"
            ar = await client.post("/api/action", json=payload)
            assert ar.status_code == 200, ar.text
        await client.post(
            "/api/post-survey",
            json={
                "sessionId": s["sessionId"],
                "payload": post_survey_v7_all_threes(),
            },
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
    assert cm["actionsZh"] == ["原样发送", "编辑后发送", "弃用并重写", "升级处理"]
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
            **_action_v7_extras(),
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
    assert "action_id" in text and "final_reply_text" in text
    assert "已修改的中文回复" in text
    assert "edit_distance" in text
    assert "gold_action_match" in text


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
