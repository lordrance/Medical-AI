from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class LLMResponse(BaseModel):
    text: str
    model: str
    provider: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int


class LLMUnavailable(Exception):
    """Raised when an LLM call cannot be made (provider disabled or upstream error)."""


class LLMProvider(Protocol):
    name: str
    model: str

    async def generate(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """Generate a completion. Raise LLMUnavailable on failure."""
        ...

    async def health(self) -> bool:
        """Lightweight health check; should not raise on disabled provider."""
        ...
