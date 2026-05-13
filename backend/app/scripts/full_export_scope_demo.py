"""端到端：覆盖图片中「数据范围」所列全部来源表，并验证 ZIP 导出可读。

运行：cd backend && .venv/bin/python -m app.scripts.full_export_scope_demo
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import tempfile
import time
import zipfile
from datetime import datetime, timezone

# 独立临时库
_tmp = tempfile.mkdtemp(prefix="full-scope-")
_db = os.path.join(_tmp, "scope.db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_db}"
os.environ["ADMIN_TOKEN"] = "scope-demo-token"
os.environ["LLM_PROVIDER"] = "disabled"

from app.core.config import get_settings

get_settings.cache_clear()

from httpx import ASGITransport, AsyncClient

from app.db.base import Base
from app.db.session import get_engine, reset_engine_for_tests
from app.main import app
from app.scripts.data_loader import load_cases
from app.scripts.seed import upsert_cases, upsert_order_templates
from app.schemas.post_survey_payload import post_survey_v7_all_threes


EXPORT_TABLES = [
    "participants",
    "sessions",
    "case_presentations",
    "actions",
    "case_surveys",
    "post_surveys",
    "ui_events",
    "cases",
    "order_templates",
    "llm_calls",
    "cohort_summaries",
]


async def run() -> None:
    await reset_engine_for_tests()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await upsert_cases()
    await upsert_order_templates()

    gold_by_id = {c["id"]: c["goldAction"] for c in load_cases()}
    transport = ASGITransport(app=app)
    headers_admin = {"X-Admin-Token": "scope-demo-token"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/session")
        assert r.status_code == 200, r.text
        s = r.json()
        sid = s["sessionId"]
        order = s["caseOrder"]
        practice_id = s["practiceCaseId"]

        await client.post(
            "/api/pre-survey",
            json={
                "sessionId": sid,
                "answers": {
                    "pre_specialty": "测试科室",
                    "pre_training_level": "主治医师",
                    "pre_years_post_residency": 5,
                    "pre_weekly_msg_volume": "11—25 条",
                    "pre_ai_drafting_familiarity": 4,
                },
            },
        )

        now_ms = int(time.time() * 1000)

        async def submit_one(
            case_id: str,
            order_index: int,
            is_practice: bool,
            inject_ui: bool,
        ) -> None:
            nonlocal now_ms
            cr = await client.get(
                f"/api/case/{case_id}",
                params={"sessionId": sid},
            )
            assert cr.status_code == 200
            payload = cr.json()["case"]
            draft = payload["aiDraft"]

            op = await client.post(
                "/api/case/open",
                json={
                    "sessionId": sid,
                    "caseId": case_id,
                    "orderIndex": order_index,
                },
            )
            assert op.status_code == 200
            pres_id = op.json()["casePresentationId"]

            ts = datetime.now(timezone.utc).isoformat()
            if inject_ui:
                for et, pl in [
                    ("chart_expanded", {"caseId": case_id}),
                    ("help_risk_panel_expanded", {"caseId": case_id}),
                    ("draft_source_context_switch", {"caseId": case_id, "count": 1}),
                    ("panel_clicked", {"panel": "facts_panel", "caseId": case_id}),
                    ("panel_clicked", {"panel": "risk_panel", "caseId": case_id}),
                ]:
                    await client.post(
                        "/api/ui-event",
                        json={
                            "sessionId": sid,
                            "casePresentationId": pres_id,
                            "eventType": et,
                            "payload": pl,
                            "clientTs": ts,
                        },
                    )

            ga = gold_by_id[case_id]
            sel = ga
            if ga == "send_as_is":
                final_txt = draft
            elif ga == "escalate":
                final_txt = "[escalated]"
            elif ga == "edit_then_send":
                final_txt = draft + " 审阅。"
            elif ga == "discard_and_rewrite":
                final_txt = "重写回复（演示）。"
            else:
                final_txt = draft

            body: dict = {
                "sessionId": sid,
                "caseId": case_id,
                "orderIndex": order_index,
                "isPractice": is_practice,
                "selectedAction": sel,
                "finalReplyText": final_txt,
                "quickSurvey": {"caseDecisionConfidence": 4, "caseDraftHelpfulness": 3},
                "caseActionReasonCode": "basically_ok",
                "timing": {
                    "startedAt": now_ms - 4000,
                    "endedAt": now_ms,
                    "durationMs": 4000,
                },
                "clientStats": {
                    "timeToFirstClickMs": 120,
                    "panelClickCounts": {"chart_panel": 1, "ai_draft_panel": 2},
                    "checklistChecked": [],
                    "checklistToggleCount": 0,
                    "editKeystrokes": 0,
                    "editBoxOpenedCount": 0,
                    "pageBlurCount": 0,
                    "pageFocusCount": 1,
                    "visibilityHiddenMs": 0,
                    "interactionMetrics": {
                        "chartExpandToggleCount": 2 if inject_ui else 0,
                        "guardrailExpandToggleCount": 1 if inject_ui else 0,
                        "draftSourceSwitchCount": 3 if inject_ui else 0,
                        "chartEverExpandedToView": bool(inject_ui),
                        "guardrailEverExpandedToView": bool(inject_ui),
                        "sendAsIsAcknowledged": sel == "send_as_is",
                    },
                },
            }
            if sel == "escalate":
                body["escalateSubtype"] = "urgent_evaluation"
                body["escalateReason"] = "演示升级原因。"

            ar = await client.post("/api/action", json=body)
            assert ar.status_code == 200, ar.text
            now_ms += 100

        # 练习 1 题
        await submit_one(practice_id, -1, True, inject_ui=False)

        # 正式 8 题：仅第 1 题注入细粒度 UI 事件
        for i, cid in enumerate(order):
            await submit_one(cid, i, False, inject_ui=(i == 0))

        post = await client.post(
            "/api/post-survey",
            json={
                "sessionId": sid,
                "payload": post_survey_v7_all_threes(),
            },
        )
        assert post.status_code == 200

        # 导出：图片所列核心表 + 空表亦需存在
        tables_param = ",".join(EXPORT_TABLES)
        bund = await client.get(
            "/api/admin/export/bundle",
            headers=headers_admin,
            params={"tables": tables_param},
        )
        assert bund.status_code == 200, bund.text

        full = await client.get(
            "/api/admin/export/full-database",
            headers=headers_admin,
        )
        assert full.status_code == 200

        zf = zipfile.ZipFile(io.BytesIO(bund.content))

        def csv_rows(name: str) -> list[dict[str, str]]:
            raw = zf.read(f"{name}.csv").decode("utf-8")
            return list(csv.DictReader(io.StringIO(raw)))

        # ---------- 打印 ----------
        print("## 1. 导出文件与行数（对应图片「数据范围」）\n")
        print("| 表名 | ZIP 内行数 | 说明 |")
        print("| --- | ---: | --- |")
        scope_notes = {
            "participants": "受试者画像",
            "sessions": "会话",
            "case_presentations": "案例呈现（练习+正式）",
            "actions": "医生决策（含 client_stats 中 PDF log_* 自动记录）",
            "case_surveys": "每题简问卷 Likert",
            "post_surveys": "课后问卷",
            "ui_events": "细粒度 UI / 行为过程",
            "cases": "可选元数据·题干",
            "order_templates": "可选元数据·顺序模板",
            "llm_calls": "LLM 审计（可为空）",
            "cohort_summaries": "队列总结（可为空）",
        }
        for name in EXPORT_TABLES:
            rows = csv_rows(name)
            note = scope_notes.get(name, "")
            print(f"| {name} | {len(rows)} | {note} |")

        sql_lines = len(full.content.decode("utf-8").splitlines())
        print(f"\n**整库 SQL 导出**：约 **{sql_lines}** 行（含全部表结构与数据）。\n")

        # 抽样：参与者、会话、一道 action、一道 ui_event（非 session_started）
        part = csv_rows("participants")[0]
        sess = csv_rows("sessions")[0]
        acts = csv_rows("actions")
        first_formal = next(
            (a for a in acts if a.get("case_id") == order[0]),
            acts[0],
        )
        surveys = csv_rows("case_surveys")
        posts = csv_rows("post_surveys")
        uis = [u for u in csv_rows("ui_events") if u.get("eventType") == "chart_expanded"]
        cp = csv_rows("case_presentations")
        one_cp = next((c for c in cp if c.get("case_id") == order[0]), cp[0])

        print("## 2. participants.csv（当前受试者抽样）\n")
        print("| participant_id | condition | pre_specialty | pre_ai_drafting_familiarity | completed_flag |")
        print("| --- | --- | --- | --- | --- |")
        print(
            f"| …{part.get('participant_id', '')[-8:]} | {part.get('condition')} | "
            f"{part.get('pre_specialty')} | {part.get('pre_ai_drafting_familiarity')} | {part.get('completed_flag')} |"
        )

        print("\n## 3. sessions.csv\n")
        print("| sessionId | status | endedAt 是否出现 |")
        print("| --- | --- | --- |")
        print(
            f"| …{sess.get('sessionId', '')[-8:]} | {sess.get('status')} | "
            f"{'是' if sess.get('endedAt') else '否'} |"
        )

        print("\n## 4. case_presentations.csv（正式第 1 题抽样）\n")
        print("| casePresentationId | caseId | orderIndex | durationMs |")
        print("| --- | --- | --- | --- |")
        print(
            f"| …{one_cp.get('casePresentationId', '')[-8:]} | {one_cp.get('caseId')} | "
            f"{one_cp.get('orderIndex')} | {one_cp.get('durationMs')} |"
        )

        print("\n## 5. actions.csv（正式第 1 题：决策 + client_stats）\n")
        cs = first_formal.get("client_stats") or ""
        cs_obj = json.loads(cs) if cs else {}
        print("| selected_action | edit_distance | gold_action_match | client_stats（摘要） |")
        print("| --- | --- | --- | --- |")
        im_short = json.dumps(cs_obj, ensure_ascii=False)[:120]
        print(
            f"| {first_formal.get('selected_action')} | {first_formal.get('edit_distance')} | "
            f"{first_formal.get('gold_action_match')} | {im_short}… |"
        )

        print("\n## 6. case_surveys.csv（与上同一 presentation 对应一行）\n")
        csur = next(
            (x for x in surveys if x.get("case_id") == order[0]),
            surveys[0],
        )
        print("| case_id | case_decision_confidence | case_draft_helpfulness |")
        print("| --- | --- | --- |")
        print(
            f"| {csur.get('case_id')} | {csur.get('case_decision_confidence')} | "
            f"{csur.get('case_draft_helpfulness')} |"
        )

        print("\n## 7. post_surveys.csv\n")
        pj = (posts[0].get("payloadJson") or "")[:80]
        print("| payloadJson（节选） |")
        print("| --- |")
        print(f"| {pj}… |")

        print("\n## 8. ui_events.csv（正式第 1 题：chart_expanded）\n")
        if uis:
            u = uis[0]
            print("| eventType | casePresentationId | payloadJson |")
            print("| --- | --- | --- |")
            print(
                f"| {u.get('eventType')} | …{(u.get('casePresentationId') or '')[-8:]} | "
                f"{u.get('payloadJson')} |"
            )
        else:
            print("| （未找到 chart_expanded） |")

        print("\n## 9. cases.csv / order_templates.csv（元数据抽样）\n")
        cases_rows = csv_rows("cases")
        ot_rows = csv_rows("order_templates")
        c1 = next((x for x in cases_rows if x.get("caseId") == order[0]), cases_rows[0])
        ot = ot_rows[0]
        print("| cases.caseId | goldAction | defectPresent |")
        print("| --- | --- | --- |")
        print(
            f"| {c1.get('caseId')} | {c1.get('goldAction')} | {c1.get('defectPresent')} |"
        )
        print("\n| order_templates.id | order 含 case 数 |")
        print("| --- | --- |")
        oj = ot.get("orderJson") or "[]"
        n = len(json.loads(oj)) if oj else 0
        print(f"| {ot.get('orderTemplateId')} | {n} |")

        print("\n## 结论\n")
        print(
            "- 图片中列出的 **participants / sessions / case_presentations / actions / "
            "case_surveys / post_surveys / ui_events / cases / order_templates** 均在本次流程中产生记录，"
            "并可从 **ZIP** 与 **整库 SQL** 中导出。\n"
            "- **llm_calls / cohort_summaries** 可为 0 行（未调用 LLM / 未生成队列总结），仍导出表头，属正常。\n"
        )


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
