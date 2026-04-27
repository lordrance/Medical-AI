from __future__ import annotations

from app.llm.base import LLMProvider, LLMResponse, LLMUnavailable


class DisabledProvider:
    """A provider that refuses any call. Used when LLM_PROVIDER=disabled."""

    name: str = "disabled"
    model: str = "disabled"

    async def generate(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        raise LLMUnavailable(
            "LLM provider is disabled. Set LLM_PROVIDER=deepseek and provide DEEPSEEK_API_KEY."
        )

    async def health(self) -> bool:
        return False


_assert_protocol: LLMProvider = DisabledProvider()  # type: ignore[assignment]
