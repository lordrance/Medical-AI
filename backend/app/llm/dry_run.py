from __future__ import annotations

import time

from app.llm.base import LLMResponse


class DryRunProvider:
    """Returns canned, deterministic responses without calling any external API.

    Useful when developing without a real API key. Activated via env
    `LLM_DRY_RUN=true` or when DEEPSEEK_API_KEY is missing while
    LLM_PROVIDER=deepseek.
    """

    name: str = "dry_run"
    model: str = "dry-run-v1"

    async def generate(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        start = time.monotonic()
        # Tiny deterministic mock that quotes the user prompt.
        text = (
            "[DRY-RUN 模拟回复] 这是来自 dry-run provider 的模拟内容，"
            "未调用任何外部模型。\n\n"
            f"系统提示长度：{len(system)} 字\n"
            f"用户提示长度：{len(user)} 字\n"
            "—— 上线前请在 .env 配置 DEEPSEEK_API_KEY 并把 LLM_PROVIDER 设为 deepseek。"
        )
        latency = int((time.monotonic() - start) * 1000)
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.name,
            prompt_tokens=len(system) + len(user),
            completion_tokens=len(text),
            latency_ms=latency,
        )

    async def health(self) -> bool:
        return True
