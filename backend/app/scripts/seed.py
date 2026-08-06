"""
================================================================================
文件作用：把题库 JSON 灌进数据库（seed = 播种）
================================================================================

数据库刚建好时是空的，题目、顺序模板都得先塞进去，医生才有题可做。
这个脚本干的就是这件事。

什么时候会跑：
  * 容器每次启动时自动跑一遍（docker/entrypoint.sh 里，SEED_ON_START=true）
  * 你改了 cases.json 之后手动跑：cd backend && python -m app.scripts.seed

★ 「幂等」是这个脚本最重要的性质：重复跑任意多次，结果都一样。
  已存在的题目就更新内容，不存在的才新建。所以容器天天重启也不会
  产生重复数据。

★ 注意：改了题目内容并重新 seed 之后，**必须重启后端**。
  因为题目内容被缓存在每个进程的内存里（见 core/cache.py），
  不重启的话老进程还在发旧题目。

--------------------------------------------------------------------------------
本文件的代码块（从上到下）：
--------------------------------------------------------------------------------
  第 1 块  ensure_schema()          建表（只在开发时用）
  第 2 块  upsert_cases()           ★ 灌题目
  第 3 块  upsert_order_templates() 灌顺序模板
  第 4 块  list_cases()             列出库里现有的题目编号
  第 5 块  main()                   把上面几步串起来
================================================================================
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.base import Base
from app.db.models import Case, OrderTemplate
from app.db.session import get_engine, get_session_factory
from app.scripts.data_loader import load_cases, load_order_templates


# ── 第 1 块：建表 ────────────────────────────────────────────────────────
async def ensure_schema() -> None:
    """Create tables if missing (dev-only convenience).

    中文：表不存在就照着 models.py 建出来。
    ★ 只在本地开发时管用。生产环境的表结构由 alembic 迁移脚本管理，
      因为生产库里有真实数据，不能简单地"没有就建"。
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── 第 2 块：灌题目 ★ ────────────────────────────────────────────────────
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


# ── 第 3 块：灌顺序模板 ──────────────────────────────────────────────────
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


# ── 第 4 块：列出现有题目 ────────────────────────────────────────────────
async def list_cases() -> list[str]:
    """返回库里所有题目的编号。给测试和排查用。"""
    factory = get_session_factory()
    async with factory() as session:
        rows = await session.execute(select(Case.id))
        return [r[0] for r in rows.all()]


# ── 第 5 块：串起来 ──────────────────────────────────────────────────────
async def main() -> None:
    """命令行入口：建表 → 灌题目 → 灌顺序 → 打印结果。"""
    await ensure_schema()
    n_cases = await upsert_cases()
    n_tpl = await upsert_order_templates()
    print(f"[seed] cases: {n_cases}")
    print(f"[seed] order templates: {n_tpl}")
    print("[seed] done")


# 这一行的意思是"只有直接运行本文件时才执行 main()"。
# 别的文件 import 这个模块时（比如测试要用 upsert_cases），不会触发。
if __name__ == "__main__":
    asyncio.run(main())
