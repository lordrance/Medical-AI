"""Seed cases & order templates into the configured database.

Run: `python -m app.scripts.seed`.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.base import Base
from app.db.models import Case, OrderTemplate
from app.db.session import get_engine, get_session_factory
from app.scripts.data_loader import load_cases, load_order_templates


async def ensure_schema() -> None:
    """Create tables if missing (dev-only convenience)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def upsert_cases() -> int:
    factory = get_session_factory()
    cases = load_cases()
    async with factory() as session:
        for c in cases:
            existing = await session.get(Case, c["id"])
            data = dict(
                id=c["id"],
                is_practice=c["isPractice"],
                risk_level=c["riskLevel"],
                defect_present=c["defectPresent"],
                defect_type=c.get("defectType"),
                purpose=c.get("purpose"),
                patient_message=c["patientMessage"],
                chart_snapshot=c["chartSnapshot"],
                ai_draft=c["aiDraft"],
                facts_used=c["guardrail"]["factsUsed"],
                risk_cue=c["guardrail"]["riskCue"],
                checklist=c["guardrail"]["checklist"],
                gold_action=c["goldAction"],
                gold_action_alternates=c.get("goldActionAlternates", []),
                language="zh-CN",
            )
            if existing is None:
                session.add(Case(**data))
            else:
                for k, v in data.items():
                    setattr(existing, k, v)
        await session.commit()
    return len(cases)


async def upsert_order_templates() -> int:
    factory = get_session_factory()
    templates = load_order_templates()["templates"]
    async with factory() as session:
        for t in templates:
            existing = await session.get(OrderTemplate, t["id"])
            if existing is None:
                session.add(OrderTemplate(id=t["id"], order=t["order"]))
            else:
                existing.order = t["order"]
        await session.commit()
    return len(templates)


async def list_cases() -> list[str]:
    factory = get_session_factory()
    async with factory() as session:
        rows = await session.execute(select(Case.id))
        return [r[0] for r in rows.all()]


async def main() -> None:
    await ensure_schema()
    n_cases = await upsert_cases()
    n_tpl = await upsert_order_templates()
    print(f"[seed] cases: {n_cases}")
    print(f"[seed] order templates: {n_tpl}")
    print("[seed] done")


if __name__ == "__main__":
    asyncio.run(main())
