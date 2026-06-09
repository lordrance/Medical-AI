from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.llm.disabled import DisabledProvider
from app.llm.dry_run import DryRunProvider
from app.llm.factory import get_provider
from app.llm.prompts import load_prompt, render_template
from app.scripts.seed import upsert_cases, upsert_order_templates


@pytest.fixture(autouse=True)
async def _seed():
    await upsert_cases()
    await upsert_order_templates()


def _set_settings(**overrides):
    """Override settings via the lru_cache."""
    s = get_settings()
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def test_load_prompt_files_have_both_sections() -> None:
    for name in ("case_draft", "participant_summary", "cohort_summary"):
        sys_, user_ = load_prompt(name)
        assert sys_, f"{name} system empty"
        assert user_, f"{name} user empty"
        assert "{{" in user_, f"{name} user template should have placeholder"


def test_render_template_replaces_variables() -> None:
    out = render_template("hello {{x}} world {{y}}", {"x": "1", "y": "2"})
    assert out == "hello 1 world 2"


def test_factory_returns_disabled_when_provider_disabled() -> None:
    _set_settings(LLM_PROVIDER="disabled")
    p = get_provider()
    assert isinstance(p, DisabledProvider)


def test_factory_falls_back_to_dry_run_when_no_key() -> None:
    _set_settings(LLM_PROVIDER="deepseek", DEEPSEEK_API_KEY=None, LLM_DRY_RUN=False)
    p = get_provider()
    assert isinstance(p, DryRunProvider)
    _set_settings(LLM_PROVIDER="disabled")  # reset


def test_factory_dry_run_explicit() -> None:
    _set_settings(LLM_PROVIDER="deepseek", DEEPSEEK_API_KEY="sk-test", LLM_DRY_RUN=True)
    p = get_provider()
    assert isinstance(p, DryRunProvider)
    _set_settings(LLM_PROVIDER="disabled", LLM_DRY_RUN=False)


@pytest.mark.asyncio
async def test_disabled_provider_raises() -> None:
    from app.llm.base import LLMUnavailable

    p = DisabledProvider()
    with pytest.raises(LLMUnavailable):
        await p.generate(system="", user="")


@pytest.mark.asyncio
async def test_dry_run_provider_returns_canned_text() -> None:
    p = DryRunProvider()
    r = await p.generate(system="hello", user="world")
    assert "[DRY-RUN" in r.text
    assert r.provider == "dry_run"
    assert r.model == "dry-run-v1"
    assert r.prompt_tokens is not None


@pytest.mark.asyncio
async def test_admin_llm_endpoints_require_token(client: AsyncClient) -> None:
    r1 = await client.post(
        "/api/admin/llm/case-draft",
        json={"patientMessage": "x", "chartSnapshot": {}},
    )
    assert r1.status_code == 401
    r2 = await client.post(
        "/api/admin/llm/participant-summary", json={"participantId": "x"}
    )
    assert r2.status_code == 401
    r3 = await client.post("/api/admin/llm/cohort-summary")
    assert r3.status_code == 401


@pytest.mark.asyncio
async def test_admin_llm_case_draft_with_dry_run(
    client: AsyncClient, admin_token: str
) -> None:
    _set_settings(LLM_PROVIDER="deepseek", DEEPSEEK_API_KEY=None, LLM_DRY_RUN=False)
    r = await client.post(
        "/api/admin/llm/case-draft",
        headers={"X-Admin-Token": admin_token},
        json={
            "patientMessage": "医生，我从昨天开始头痛。",
            "chartSnapshot": {"年龄": 30, "性别": "男"},
        },
    )
    _set_settings(LLM_PROVIDER="disabled")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "dry_run"
    assert "[DRY-RUN" in body["text"]
    assert body["model"] == "dry-run-v1"


@pytest.mark.asyncio
async def test_admin_llm_returns_503_when_disabled(
    client: AsyncClient, admin_token: str
) -> None:
    _set_settings(LLM_PROVIDER="disabled")
    r = await client.post(
        "/api/admin/llm/case-draft",
        headers={"X-Admin-Token": admin_token},
        json={"patientMessage": "x", "chartSnapshot": {}},
    )
    assert r.status_code == 503
    assert "disabled" in r.json()["detail"]


@pytest.mark.asyncio
async def test_admin_llm_cohort_summary_records_summary(
    client: AsyncClient, admin_token: str
) -> None:
    _set_settings(LLM_PROVIDER="deepseek", DEEPSEEK_API_KEY=None, LLM_DRY_RUN=False)
    r = await client.post(
        "/api/admin/llm/cohort-summary",
        headers={"X-Admin-Token": admin_token},
    )
    _set_settings(LLM_PROVIDER="disabled")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "summaryText" in body
    # Verify it landed in cohort_summaries + llm_calls
    from sqlalchemy import select
    from app.db.models import CohortSummary, LLMCall
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as s:
        cs = (await s.execute(select(CohortSummary))).scalars().all()
        calls = (await s.execute(select(LLMCall))).scalars().all()
        assert len(cs) >= 1
        assert any(c.purpose == "cohort_summary" for c in calls)


@pytest.mark.asyncio
async def test_admin_llm_health(client: AsyncClient, admin_token: str) -> None:
    _set_settings(LLM_PROVIDER="disabled")
    r = await client.get(
        "/api/admin/llm/health",
        headers={"X-Admin-Token": admin_token},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "disabled"
    assert body["ok"] is False


# --- Regression: LLM calls from participant-facing case rendering must be audited ---


async def _fetch_llm_calls():
    from sqlalchemy import select
    from app.db.models import LLMCall
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as s:
        return (await s.execute(select(LLMCall))).scalars().all()


@pytest.mark.asyncio
async def test_case_render_audits_llm_call_even_when_provider_disabled(
    client: AsyncClient,
) -> None:
    """Bug #1 regression: participant-side case_draft LLM calls must be
    recorded in llm_calls even when the provider is disabled and the system
    falls back to seeded text. (Note: V4 removes the guardrail panel so
    risk_tip is no longer triggered — only case_draft remains.)"""
    _set_settings(LLM_PROVIDER="disabled")
    s = (await client.post("/api/session")).json()

    # case_practice is the only non-defect case in the seed (defect_present=False),
    # so it actually exercises _generate_case_draft.
    r = await client.get(
        f"/api/case/case_practice?sessionId={s['sessionId']}"
    )
    assert r.status_code == 200

    calls = await _fetch_llm_calls()
    purposes = {c.purpose for c in calls}
    assert "case_draft" in purposes, "case_draft LLM call not audited"
    # V4: guardrail panel removed; risk_tip must NOT be invoked anymore.
    assert "risk_tip" not in purposes, "risk_tip should not fire in V4"
    # The case_draft call should be marked as an error since provider is disabled
    for c in calls:
        assert c.error, f"expected error recorded for {c.purpose}, got empty"
        assert c.provider == "disabled"


@pytest.mark.asyncio
async def test_defect_case_skips_case_draft_llm_call(client: AsyncClient) -> None:
    """For defect_present cases we MUST NOT invoke the LLM for case_draft
    (otherwise the model would 'fix' the seeded flaw).

    case_06 is the V3 single-escalation case with defectPresent=true."""
    _set_settings(LLM_PROVIDER="disabled")
    s = (await client.post("/api/session")).json()
    r = await client.get(f"/api/case/case_06?sessionId={s['sessionId']}")
    assert r.status_code == 200

    calls = await _fetch_llm_calls()
    purposes = [c.purpose for c in calls]
    assert "case_draft" not in purposes, "defect case must skip case_draft LLM"
    # V4: no risk_tip invocation at all
    assert "risk_tip" not in purposes


@pytest.mark.asyncio
async def test_admin_participant_summary_audits_failure(
    client: AsyncClient, admin_token: str
) -> None:
    """Bug #2 regression: participant_summary must record the failed LLM call
    when the provider raises LLMUnavailable, mirroring case_draft behaviour."""
    _set_settings(LLM_PROVIDER="disabled")
    # First create a participant so the endpoint reaches the LLM call
    s = (await client.post("/api/session")).json()
    r = await client.post(
        "/api/admin/llm/participant-summary",
        headers={"X-Admin-Token": admin_token},
        json={"participantId": s["participantId"]},
    )
    assert r.status_code == 503

    calls = await _fetch_llm_calls()
    err_rows = [c for c in calls if c.purpose == "participant_summary" and c.error]
    assert err_rows, "failed participant_summary call must be audited"


@pytest.mark.asyncio
async def test_admin_cohort_summary_audits_failure(
    client: AsyncClient, admin_token: str
) -> None:
    """Bug #2 regression: cohort_summary error path must also be audited."""
    _set_settings(LLM_PROVIDER="disabled")
    r = await client.post(
        "/api/admin/llm/cohort-summary",
        headers={"X-Admin-Token": admin_token},
    )
    assert r.status_code == 503

    calls = await _fetch_llm_calls()
    err_rows = [c for c in calls if c.purpose == "cohort_summary" and c.error]
    assert err_rows, "failed cohort_summary call must be audited"
