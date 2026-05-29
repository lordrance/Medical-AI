from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import Case, OrderTemplate
from app.db.session import get_session_factory
from app.scripts.seed import upsert_cases, upsert_order_templates


@pytest.mark.asyncio
async def test_seed_cases_and_templates() -> None:
    n_cases = await upsert_cases()
    n_tpl = await upsert_order_templates()
    assert n_cases == 9  # 1 practice + 8 formal
    assert n_tpl == 4

    factory = get_session_factory()
    async with factory() as session:
        cases = (await session.execute(select(Case))).scalars().all()
        practice = [c for c in cases if c.is_practice]
        formal = [c for c in cases if not c.is_practice]
        assert len(practice) == 1
        assert len(formal) == 8
        # Chinese content sanity check — V3 harder cases
        c01 = next(c for c in formal if c.id == "case_01")
        assert "鼻塞" in c01.patient_message  # low-risk calibration anchor
        assert c01.gold_action == "send_as_is"
        assert c01.defect_present is False
        assert c01.language == "zh-CN"
        # The single escalation case in V3 is case_06 (GI bleed risk under NSAID)
        c06 = next(c for c in formal if c.id == "case_06")
        assert c06.gold_action == "escalate"
        assert c06.defect_present is True

        tpls = (await session.execute(select(OrderTemplate))).scalars().all()
        assert len(tpls) == 4
        for t in tpls:
            assert len(t.order) == 8


@pytest.mark.asyncio
async def test_seed_is_idempotent() -> None:
    """Running seed twice must not duplicate rows."""
    await upsert_cases()
    await upsert_order_templates()
    await upsert_cases()  # second run
    await upsert_order_templates()

    factory = get_session_factory()
    async with factory() as session:
        n_cases = (await session.execute(select(Case))).scalars().all()
        n_tpl = (await session.execute(select(OrderTemplate))).scalars().all()
        assert len(n_cases) == 9
        assert len(n_tpl) == 4


@pytest.mark.asyncio
async def test_v3_gold_action_distribution() -> None:
    """V3 加难版 PDF 规定的 gold-action 分布（避免「每题一个唯一动作」的旧模式）：
        1× send_as_is, 3× edit_then_send, 3× discard_and_rewrite, 1× escalate
    并且每个 case 必须给出至少 1 个 goldActionAlternates，反映 PDF
    「主接受动作 + 次接受动作」的双轨设计。"""
    await upsert_cases()
    factory = get_session_factory()
    async with factory() as session:
        formal = [
            c for c in (await session.execute(select(Case))).scalars().all()
            if not c.is_practice
        ]
        assert len(formal) == 8

        counts: dict[str, int] = {}
        for c in formal:
            counts[c.gold_action] = counts.get(c.gold_action, 0) + 1
            assert len(c.gold_action_alternates) >= 1, (
                f"case {c.id} 缺少 goldActionAlternates（PDF 要求每题至少 1 个次接受动作）"
            )

        assert counts == {
            "send_as_is": 1,
            "edit_then_send": 3,
            "discard_and_rewrite": 3,
            "escalate": 1,
        }, f"gold action distribution drift: {counts}"
