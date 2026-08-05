"""LLM call audit logging.

Shared by all callers (case rendering, admin tools) so every provider invocation
— including failed ones — is durably recorded in the `llm_calls` table.

★ 中文：调用 AI 的「记账本」。

规矩：**每一次调用 AI 都必须经过这里记一笔，成功失败都要记。**
只在成功时记账是曾经修过的一个真 bug（commit bc933f9），别再犯。

为什么这条规矩重要：
  1. 研究可复现性——审稿人问「你的总结是怎么生成的」，你得拿得出
     每一次的 prompt 原文和模型返回。
  2. 成本和故障排查——调了多少次、失败率多少、慢在哪里。

★ 注意：V4 的**医生端完全不调用 AI**（题目文本是写死的）。
所以 llm_calls 表现在是 0 行。只有你在后台点「生成研究总结」时才会用到。
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
    error: str | None = None,   # ★ 失败时把错误信息填这里，照样要记一笔
) -> None:
    """记一笔 AI 调用。

    参数里的 `*` 表示后面全是关键字参数——调用时必须写清楚
    `purpose="cohort_summary"` 这样，不能靠位置传，免得传错顺序。
    """
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
