"""LLM call audit logging.

Shared by all callers (case rendering, admin tools) so every provider invocation
— including failed ones — is durably recorded in the `llm_calls` table.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LLMCall


async def record_llm_call(
    db: AsyncSession,
    *,
    purpose: str,
    provider: str,
    model: str,
    prompt_text: str,
    response_text: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    latency_ms: int,
    error: str | None = None,
) -> None:
    db.add(
        LLMCall(
            purpose=purpose,
            provider=provider,
            model=model,
            prompt_text=prompt_text,
            response_text=response_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            error=error,
        )
    )
    await db.commit()
