"""Demo: seed DB, record ui_events + action, verify exports.

Run: cd backend && .venv/bin/python -m app.scripts.showcase_export_demo
"""

from __future__ import annotations

import asyncio
import csv
import io
import os
import tempfile
import time
import zipfile

from datetime import datetime, timezone

_tmp = tempfile.mkdtemp(prefix="export-demo-")
_db = os.path.join(_tmp, "demo.db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_db}"
os.environ["ADMIN_TOKEN"] = "demo-admin-token"
os.environ["LLM_PROVIDER"] = "disabled"

from app.core.config import get_settings

get_settings.cache_clear()

from httpx import ASGITransport, AsyncClient

from app.db.base import Base
from app.db.session import get_engine, reset_engine_for_tests
from app.main import app
from app.scripts.seed import upsert_cases, upsert_order_templates


async def run() -> None:
    await reset_engine_for_tests()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await upsert_cases()
    await upsert_order_templates()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/session")
        sid = r.json()["sessionId"]
        cid = r.json()["caseOrder"][0]

        op = await client.post(
            "/api/case/open",
            json={"sessionId": sid, "caseId": cid, "orderIndex": 0},
        )
        pres_id = op.json()["casePresentationId"]

        ts = datetime.now(timezone.utc).isoformat()
        for et, payload in [
            ("chart_expanded", {"caseId": cid}),
            ("help_risk_panel_expanded", {"caseId": cid}),
            ("draft_source_context_switch", {"caseId": cid, "count": 1}),
            ("panel_clicked", {"panel": "facts_panel", "caseId": cid}),
            ("panel_clicked", {"panel": "risk_panel", "caseId": cid}),
        ]:
            await client.post(
                "/api/ui-event",
                json={
                    "sessionId": sid,
                    "casePresentationId": pres_id,
                    "eventType": et,
                    "payload": payload,
                    "clientTs": ts,
                },
            )

        cr = await client.get(f"/api/case/{cid}?sessionId={sid}")
        draft = cr.json()["case"]["aiDraft"]
        now = int(time.time() * 1000)

        await client.post(
            "/api/action",
            json={
                "sessionId": sid,
                "caseId": cid,
                "orderIndex": 0,
                "selectedAction": "send_as_is",
                "finalReplyText": draft,
                "quickSurvey": {"caseDecisionConfidence": 4, "caseDraftHelpfulness": 4},
                "caseActionReasonCode": "basically_ok",
                "timing": {
                    "startedAt": now - 8000,
                    "endedAt": now,
                    "durationMs": 8000,
                },
                "clientStats": {
                    "interactionMetrics": {
                        "chartExpandToggleCount": 2,
                        "guardrailExpandToggleCount": 1,
                        "draftSourceSwitchCount": 3,
                        "chartEverExpandedToView": True,
                        "guardrailEverExpandedToView": True,
                        "sendAsIsAcknowledged": True,
                    },
                    "panelClickCounts": {
                        "chart_panel": 2,
                        "guardrail_panel": 1,
                    },
                },
            },
        )

        hdr = {"X-Admin-Token": "demo-admin-token"}

        full = await client.get("/api/admin/export/full-database", headers=hdr)
        assert full.status_code == 200
        sql_lines = len(full.content.decode("utf-8").splitlines())

        bund = await client.get(
            "/api/admin/export/bundle",
            headers=hdr,
            params={"tables": "actions,ui_events"},
        )
        assert bund.status_code == 200

        zf = zipfile.ZipFile(io.BytesIO(bund.content))
        actions_txt = zf.read("actions.csv").decode("utf-8")
        ui_txt = zf.read("ui_events.csv").decode("utf-8")

        def row_dicts(csv_text: str, max_rows: int = 10):
            rdr = csv.DictReader(io.StringIO(csv_text))
            out = []
            for i, row in enumerate(rdr):
                if i >= max_rows:
                    break
                out.append(dict(row))
            return out

        act_rows = row_dicts(actions_txt, 1)
        ui_rows = row_dicts(ui_txt, 10)

        print("## Export demo results\n")
        print(f"- Full SQL dump: **{sql_lines}** lines (SQLite iterdump)\n")
        print("### actions.csv (first row)\n")
        if act_rows:
            a = act_rows[0]
            slim = {
                "sessionId": a.get("sessionId"),
                "caseId": a.get("caseId"),
                "selectedAction": a.get("selectedAction"),
                "clientStatsJson_snippet": (a.get("clientStatsJson") or "")[:120] + "…",
            }
            print("| field | value |")
            print("| --- | --- |")
            for k, v in slim.items():
                print(f"| {k} | {v} |")
        print("\n### ui_events.csv (simulated rows)\n")
        print("| eventType | casePresentationId | payloadJson (truncated) |")
        print("| --- | --- | --- |")
        for u in ui_rows:
            pj = u.get("payloadJson") or ""
            print(
                f"| {u.get('eventType')} | "
                f"{u.get('casePresentationId') or ''} | "
                f"{pj[:55]}… |"
            )


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
