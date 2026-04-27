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
        # Chinese content sanity check
        c01 = next(c for c in formal if c.id == "case_01")
        assert "赖诺普利" in c01.patient_message
        assert c01.gold_action == "escalate"
        assert c01.language == "zh-CN"

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
