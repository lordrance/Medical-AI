"""Seed cases & order templates into the configured database.

Run: `python -m app.scripts.seed`.

★ 中文：把题库 JSON 灌进数据库。

什么时候会跑：
  - 容器每次启动时自动跑一遍（docker/entrypoint.sh 里，SEED_ON_START=true）
  - 你改了 cases.json 之后手动跑

★ 「幂等」：重复跑任意多次结果都一样。已存在的题目更新内容，
不存在的才新建。所以容器天天重启也不会产生重复数据。

★ 注意：改了题目内容并重新 seed 之后，**必须重启后端**。
因为题目内容被缓存在每个 worker 的内存里（见 core/cache.py），
不重启的话老 worker 还在发旧题目。
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
    """把 cases.json 里的题目写进数据库。upsert = update + insert。

    ★ 这里做的是「JSON 的 camelCase → 数据库的 snake_case」翻译。
    比如 JSON 里写 isPractice，数据库列叫 is_practice。
    """
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
                session.add(Case(**data))   # 库里没有 → 新建
            else:
                # 库里已有 → 逐字段覆盖。
                # ★ 只更新不删除：如果 cases.json 里删掉了一道题，
                # 数据库里那道题**不会**被删。这是故意的——已经有医生
                # 答过那道题了，删了会留下一堆指向空题目的孤儿数据。
                for k, v in data.items():
                    setattr(existing, k, v)
        await session.commit()
    return len(cases)


async def upsert_order_templates() -> int:
    """把 4 套题目顺序写进数据库。逻辑同上。"""
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
