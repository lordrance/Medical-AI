"""模拟用户走完全流程，并验证写入库中的内容与管理员 CSV/ZIP 导出一致。

覆盖：前测字段、案例 open、UI 事件 payload（含点击与语音相关事件名）、
动作 final_reply_text 与派生 client_stats（log_*）、案例末量表、后测（含开放式题）、
以及导出接口。

说明：真实「浏览器 Web Speech」无法在 pytest 中驱动麦克风；语音相关通过
与前端 `logEvent` 相同的 `POST /api/ui-event` 契约（voice_input_*）验证落库与导出。
"""

from __future__ import annotations

import csv
import io
import json
import uuid
import zipfile

import pytest
from httpx import AsyncClient

from app.schemas.post_survey_payload import post_survey_v7_all_threes
from app.scripts.seed import upsert_cases, upsert_order_templates


@pytest.fixture(autouse=True)
async def _seed() -> None:
    await upsert_cases()
    await upsert_order_templates()


def _action_extras() -> dict:
    return {
        "quickSurvey": {"caseDecisionConfidence": 4, "caseDraftHelpfulness": 3},
        "caseActionReasonCode": "basically_ok",
    }


@pytest.mark.asyncio
async def test_simulated_user_full_flow_records_and_exports(
    client: AsyncClient, admin_token: str
) -> None:
    tag = f"SIMU_{uuid.uuid4().hex[:12]}"
    marker_pre = f"{tag}_PRE_SPEC"
    marker_ui = f"{tag}_UI_CLICK"
    marker_final = f"{tag}_FINAL_REPLY"
    marker_open_q1 = f"{tag}_OPEN_Q1_临床场景说明"
    marker_open_q2 = f"{tag}_OPEN_Q2_信任与保障"
    marker_open_q3 = f"{tag}_OPEN_Q3_流程与责任"
    marker_voice = f"{tag}_VOICE_TRACE"

    s = (await client.post("/api/session")).json()
    sid = s["sessionId"]
    pid = s["participantId"]

    assert (
        await client.post(
            "/api/pre-survey",
            json={
                "sessionId": sid,
                "answers": {
                    "pre_specialty": marker_pre,
                    "pre_training_level": "主治医师",
                    "pre_years_post_residency": 5,
                    "pre_weekly_msg_volume": "11—25 条",
                    "pre_ai_drafting_familiarity": 4,
                },
            },
        )
    ).status_code == 200

    from app.scripts.data_loader import load_cases

    gold_by_id = {c["id"]: c["goldAction"] for c in load_cases()}
    now_ms = 1_700_000_000_000

    for i, cid in enumerate(s["caseOrder"]):
        open_r = await client.post(
            "/api/case/open",
            json={"sessionId": sid, "caseId": cid, "orderIndex": i},
        )
        assert open_r.status_code == 200, open_r.text
        pres_id = open_r.json()["casePresentationId"]

        ui_r = await client.post(
            "/api/ui-event",
            json={
                "sessionId": sid,
                "casePresentationId": pres_id,
                "eventType": "panel_clicked",
                "payload": {
                    "marker": marker_ui,
                    "caseIndex": i,
                    "caseId": cid,
                    "panel": "facts_panel",
                },
            },
        )
        assert ui_r.status_code == 200

        # 模拟前端语音按钮触发的 ui_events（与 CasePage + logEvent 一致）
        vs = await client.post(
            "/api/ui-event",
            json={
                "sessionId": sid,
                "casePresentationId": pres_id,
                "eventType": "voice_input_started",
                "payload": {
                    "caseId": cid,
                    "field": "final_reply",
                    "marker": marker_voice,
                    "caseIndex": i,
                },
            },
        )
        assert vs.status_code == 200
        if i == 0:
            ver = await client.post(
                "/api/ui-event",
                json={
                    "sessionId": sid,
                    "casePresentationId": pres_id,
                    "eventType": "voice_input_error",
                    "payload": {
                        "caseId": cid,
                        "field": "final_reply",
                        "code": "simulated_no_mic",
                        "marker": marker_voice,
                    },
                },
            )
            assert ver.status_code == 200
        ve = await client.post(
            "/api/ui-event",
            json={
                "sessionId": sid,
                "casePresentationId": pres_id,
                "eventType": "voice_input_ended",
                "payload": {
                    "caseId": cid,
                    "field": "final_reply",
                    "marker": marker_voice,
                    "caseIndex": i,
                },
            },
        )
        assert ve.status_code == 200

        cr = await client.get(f"/api/case/{cid}?sessionId={sid}")
        assert cr.status_code == 200
        case_payload = cr.json()["case"]
        ga = gold_by_id[cid]
        if ga == "send_as_is":
            final_txt = case_payload["aiDraft"] + marker_final
        elif ga == "escalate":
            final_txt = f"[escalated]{marker_final}"
        elif ga == "edit_then_send":
            final_txt = case_payload["aiDraft"] + " 已审阅。" + marker_final
        elif ga == "discard_and_rewrite":
            final_txt = f"重写回复含标记{marker_final}"
        else:
            final_txt = case_payload["aiDraft"]

        body: dict = {
            "sessionId": sid,
            "caseId": cid,
            "orderIndex": i,
            "isPractice": False,
            "selectedAction": ga,
            "finalReplyText": final_txt,
            **_action_extras(),
            "timing": {
                "startedAt": now_ms - 8000,
                "endedAt": now_ms,
                "durationMs": 8000,
            },
            "clientStats": {
                "timeToFirstClickMs": 1500,
                "panelClickCounts": {"facts_panel": 2, "chart_panel": 1},
                "editKeystrokes": 12,
                "editBoxOpenedCount": 1,
                "interactionMetrics": {
                    "draftSourceSwitchCount": 5 + i,
                    "chartEverExpandedToView": True,
                    "guardrailEverExpandedToView": bool(i % 2),
                },
            },
        }
        if ga == "escalate":
            body["escalateSubtype"] = "urgent_evaluation"
            body["escalateReason"] = f"模拟升级原因 {marker_final}"

        ar = await client.post("/api/action", json=body)
        assert ar.status_code == 200, ar.text
        now_ms += 10_000

    post_payload = dict(post_survey_v7_all_threes())
    post_payload["post_qual_ehr_redesign"] = marker_open_q1
    post_payload["post_qual_ai_autonomy"] = marker_open_q2
    post_payload["post_qual_infrastructure_impact"] = marker_open_q3

    pr = await client.post(
        "/api/post-survey",
        json={"sessionId": sid, "payload": post_payload},
    )
    assert pr.status_code == 200, pr.text
    assert pr.json()["completionCode"].startswith("AIDR-")

    headers = {"X-Admin-Token": admin_token}

    rp = await client.get("/api/admin/export", params={"table": "participants", "format": "csv"}, headers=headers)
    assert rp.status_code == 200
    assert marker_pre in rp.text
    assert pid in rp.text

    ra = await client.get("/api/admin/export", params={"table": "actions", "format": "csv"}, headers=headers)
    assert ra.status_code == 200
    assert marker_final in ra.text
    act_reader = csv.DictReader(io.StringIO(ra.text))
    act_rows = [row for row in act_reader if row.get("session_id") == sid]
    assert len(act_rows) == 8
    toggles = sorted(
        int(json.loads(row["client_stats"])["log_toggle_draft_source"])
        for row in act_rows
    )
    assert toggles == [5, 6, 7, 8, 9, 10, 11, 12]
    assert all(
        json.loads(row["client_stats"])["log_verification_clicks"] == 3 for row in act_rows
    )

    ru = await client.get("/api/admin/export", params={"table": "ui_events", "format": "csv"}, headers=headers)
    assert ru.status_code == 200
    assert marker_ui in ru.text
    assert sid in ru.text
    assert "voice_input_started" in ru.text
    assert "voice_input_ended" in ru.text
    assert "voice_input_error" in ru.text
    assert marker_voice in ru.text
    ui_reader = csv.DictReader(io.StringIO(ru.text))
    ui_for_sid = [row for row in ui_reader if row.get("sessionId") == sid]
    v_starts = [r for r in ui_for_sid if r.get("eventType") == "voice_input_started"]
    v_ends = [r for r in ui_for_sid if r.get("eventType") == "voice_input_ended"]
    assert len(v_starts) == 8 and len(v_ends) == 8
    for r in v_starts:
        pj = json.loads(r["payloadJson"] or "{}")
        assert pj.get("marker") == marker_voice
        assert pj.get("field") == "final_reply"

    rcs = await client.get("/api/admin/export", params={"table": "case_surveys", "format": "csv"}, headers=headers)
    assert rcs.status_code == 200
    cs_reader = csv.DictReader(io.StringIO(rcs.text))
    cs_for_session = [row for row in cs_reader if row.get("session_id") == sid]
    assert len(cs_for_session) == 8
    assert all(row["case_decision_confidence"] == "4" for row in cs_for_session)
    assert all(row["case_draft_helpfulness"] == "3" for row in cs_for_session)

    rpost = await client.get("/api/admin/export", params={"table": "post_surveys", "format": "csv"}, headers=headers)
    assert rpost.status_code == 200
    assert marker_open_q1 in rpost.text
    assert marker_open_q2 in rpost.text
    assert marker_open_q3 in rpost.text
    assert sid in rpost.text

    rj = await client.get(
        "/api/admin/export",
        params={"table": "post_surveys", "format": "json"},
        headers=headers,
    )
    assert rj.status_code == 200
    rows = rj.json()
    assert isinstance(rows, list)
    ours = [x for x in rows if x.get("sessionId") == sid]
    assert len(ours) == 1
    loaded = json.loads(ours[0]["payloadJson"])
    assert loaded["post_qual_ehr_redesign"] == marker_open_q1
    assert loaded["attn_post_1"] == 4

    rb = await client.get(
        "/api/admin/export/bundle",
        params={"tables": "actions,post_surveys,ui_events"},
        headers=headers,
    )
    assert rb.status_code == 200
    buf = io.BytesIO(rb.content)
    with zipfile.ZipFile(buf) as zf:
        names = set(zf.namelist())
        assert names == {"actions.csv", "post_surveys.csv", "ui_events.csv"}
        post_csv = zf.read("post_surveys.csv").decode("utf-8")
        assert marker_open_q1 in post_csv
        act_csv = zf.read("actions.csv").decode("utf-8")
        assert marker_final in act_csv
        ui_csv = zf.read("ui_events.csv").decode("utf-8")
        assert "voice_input_started" in ui_csv
        assert marker_voice in ui_csv

    rsql = await client.get("/api/admin/export/full-database", headers=headers)
    assert rsql.status_code == 200
    sql_text = rsql.text.lower()
    assert "post_surveys" in sql_text or "post_survey" in sql_text
