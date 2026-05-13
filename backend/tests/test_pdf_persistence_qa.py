"""
QA 视角：模拟用户操作后，验证「用户输入」与「自动记录 log_*」
已写入数据库且可通过 ORM / 管理导出读回。
"""

from __future__ import annotations

import csv
import io
import json
import time

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import Action, CasePresentation, CaseSurvey, Participant, UiEvent
from app.db.session import get_session_factory
from app.scripts.data_loader import load_cases
from app.scripts.seed import upsert_cases, upsert_order_templates


@pytest.fixture(autouse=True)
async def _seed() -> None:
    await upsert_cases()
    await upsert_order_templates()


async def _start_session(client: AsyncClient) -> dict:
    r = await client.post("/api/session")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_user_input_and_autolog_persist_and_readable_from_db(
    client: AsyncClient, admin_token: str
) -> None:
    """模拟：前测 → 打开案例 → UI 打点 → 提交决策（含 clientStats）→ 从 DB 与导出读回。"""
    s = await _start_session(client)
    sid = s["sessionId"]
    pid = s["participantId"]
    cid = s["caseOrder"][0]

    pre_answers = {
        "pre_specialty": "心血管内科",
        "pre_training_level": "主治医师",
        "pre_years_post_residency": 6,
        "pre_weekly_msg_volume": "11—25 条",
        "pre_ai_drafting_familiarity": 5,
    }
    r_pre = await client.post(
        "/api/pre-survey",
        json={"sessionId": sid, "answers": pre_answers},
    )
    assert r_pre.status_code == 200

    ro = await client.post(
        "/api/case/open",
        json={"sessionId": sid, "caseId": cid, "orderIndex": 0},
    )
    assert ro.status_code == 200
    pres_id = ro.json()["casePresentationId"]

    await client.post(
        "/api/ui-event",
        json={
            "sessionId": sid,
            "casePresentationId": pres_id,
            "eventType": "panel_clicked",
            "payload": {"panel": "facts_panel", "note": "qa_simulation"},
        },
    )

    draft = next(c for c in load_cases() if c["id"] == cid)["aiDraft"]
    now = int(time.time() * 1000)
    duration_ms = 12_345
    body = {
        "sessionId": sid,
        "caseId": cid,
        "orderIndex": 0,
        "selectedAction": "edit_then_send",
        "finalReplyText": draft + "【测试追加】",
        "quickSurvey": {"caseDecisionConfidence": 4, "caseDraftHelpfulness": 3},
        "caseActionReasonCode": "other",
        "caseActionReasonText": "  编码员可读的自由说明  ",
        "timing": {
            "startedAt": now - duration_ms,
            "endedAt": now,
            "durationMs": duration_ms,
        },
        "clientStats": {
            "timeToFirstClickMs": 500,
            "panelClickCounts": {
                "chart_panel": 2,
                "guardrail_panel": 1,
                "facts_panel": 3,
                "risk_panel": 4,
            },
            "editKeystrokes": 10,
            "editBoxOpenedCount": 2,
            "interactionMetrics": {
                "chartEverExpandedToView": True,
                "guardrailEverExpandedToView": True,
                "draftSourceSwitchCount": 5,
            },
            "draftScrollEventCount": 7,
            "draftScrollMaxDepthRatio": 0.42,
            "draftSectionDwellMs": 88_000,
        },
    }
    ar = await client.post("/api/action", json=body)
    assert ar.status_code == 200, ar.text

    factory = get_session_factory()
    async with factory() as db:
        pt = await db.get(Participant, pid)
        assert pt is not None
        assert pt.pre_specialty == pre_answers["pre_specialty"]
        assert pt.pre_training_level == pre_answers["pre_training_level"]
        assert pt.pre_years_post_residency == pre_answers["pre_years_post_residency"]
        assert pt.pre_weekly_msg_volume == pre_answers["pre_weekly_msg_volume"]
        assert pt.pre_ai_drafting_familiarity == pre_answers["pre_ai_drafting_familiarity"]

        stmt = (
            select(Action)
            .join(CasePresentation, Action.case_presentation_id == CasePresentation.id)
            .where(CasePresentation.id == pres_id)
            .options(selectinload(Action.presentation))
        )
        act = (await db.execute(stmt)).scalar_one()
        assert act.selected_action == "edit_then_send"
        assert act.case_action_choice == 2
        assert act.log_final_action == "编辑后发送"
        assert act.case_action_reason is not None
        assert act.case_action_reason["code"] == "other"
        assert act.case_action_reason["text"] == "编码员可读的自由说明"
        assert "【测试追加】" in act.final_reply_text

        stats = act.client_stats or {}
        assert set(stats.keys()) <= {
            "log_case_review_time",
            "log_time_to_first_action",
            "log_send_as_is",
            "log_edit_then_send",
            "log_discard_rewrite",
            "log_escalate",
            "log_edit_actions",
            "log_source_panel_open",
            "log_help_risk_panel",
            "log_toggle_draft_source",
            "log_verification_clicks",
            "log_scroll_dwell_draft",
        }
        assert stats["log_case_review_time"] == pytest.approx(12.345, rel=1e-9)
        assert stats["log_time_to_first_action"] == pytest.approx(0.5, rel=1e-9)
        assert stats["log_send_as_is"] == 0
        assert stats["log_edit_then_send"] == 1
        assert stats["log_discard_rewrite"] == 0
        assert stats["log_escalate"] == 0
        assert stats["log_edit_actions"] == 12
        assert stats["log_source_panel_open"] == 1
        assert stats["log_help_risk_panel"] == 1
        assert stats["log_toggle_draft_source"] == 5
        assert stats["log_verification_clicks"] == 10

        scroll = stats["log_scroll_dwell_draft"]
        assert isinstance(scroll, dict)
        assert scroll["scroll_event_count"] == 7
        assert scroll["max_depth_ratio"] == pytest.approx(0.42, rel=1e-9)
        assert scroll["section_dwell_sec"] == pytest.approx(88.0, rel=1e-6)

        csur = (
            await db.execute(
                select(CaseSurvey).where(CaseSurvey.case_presentation_id == pres_id)
            )
        ).scalar_one()
        assert csur.case_decision_confidence == 4
        assert csur.case_draft_helpfulness == 3

        uev = (
            await db.execute(
                select(UiEvent).where(
                    UiEvent.session_id == sid,
                    UiEvent.case_presentation_id == pres_id,
                    UiEvent.event_type == "panel_clicked",
                )
            )
        ).scalar_one()
        assert (uev.payload or {}).get("panel") == "facts_panel"

    ex = await client.get(
        "/api/admin/export",
        params={"table": "actions", "format": "csv"},
        headers={"X-Admin-Token": admin_token},
    )
    assert ex.status_code == 200
    rdr = csv.DictReader(io.StringIO(ex.text))
    rows = [row for row in rdr if row.get("case_presentation_id") == pres_id]
    assert len(rows) == 1
    row = rows[0]
    assert row["case_action_choice"] == "2"
    assert row["log_final_action"] == "编辑后发送"
    reason = json.loads(row["case_action_reason"])
    assert reason["code"] == "other"
    assert reason["text"] == "编码员可读的自由说明"
    exported_stats = json.loads(row["client_stats"])
    assert exported_stats["log_verification_clicks"] == 10
    assert "timeToFirstClickMs" not in exported_stats
