from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

from app.llm.base import LLMResponse, LLMUnavailable

logger = structlog.get_logger(__name__)


class DeepseekProvider:
    """DeepSeek API provider (uses the OpenAI-compatible chat completions API)."""

    name: str = "deepseek"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        timeout_s: float = 60.0,
    ) -> None:
        if not api_key:
            raise LLMUnavailable("DEEPSEEK_API_KEY is empty")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s

    async def generate(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        start = time.monotonic()
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        url = f"{self.base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
        except httpx.HTTPError as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.error("deepseek_http_error", error=str(e), latency_ms=latency_ms)
            raise LLMUnavailable(f"DeepSeek HTTP error: {e}") from e

        if resp.status_code != 200:
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "deepseek_api_error",
                status_code=resp.status_code,
                latency_ms=latency_ms,
                response_preview=resp.text[:200],
            )
            raise LLMUnavailable(
                f"DeepSeek API returned {resp.status_code}: {resp.text[:500]}"
            )
        try:
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.error("deepseek_parse_error", error=str(e), latency_ms=latency_ms)
            raise LLMUnavailable(f"DeepSeek bad response shape: {e}") from e

        latency = int((time.monotonic() - start) * 1000)
        logger.info(
            "deepseek_call_success",
            model=self.model,
            latency_ms=latency,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.name,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            latency_ms=latency,
        )

    async def health(self) -> bool:
        # Cheap probe: HEAD the base url; failure is acceptable.
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/")
                return r.status_code < 500
        except httpx.HTTPError:
            return False
