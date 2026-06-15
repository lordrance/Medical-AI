from __future__ import annotations

import time
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.llm.base import LLMResponse, LLMUnavailable
from app.llm.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

__all__ = ["DeepseekProvider", "CircuitBreakerOpenError"]

# Module-level circuit breaker shared across all DeepSeek requests.
_circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=300.0)


class DeepseekProvider:
    """DeepSeek API provider (uses the OpenAI-compatible chat completions API).

    Protected by a circuit breaker and tenacity exponential-backoff retry.
    """

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

        # The circuit breaker gates the entire call.  If OPEN it raises
        # CircuitBreakerOpenError without touching the network.
        return await _circuit_breaker.call(
            self._do_generate, url, body, start
        )

    async def _do_generate(
        self, url: str, body: dict[str, Any], start: float
    ) -> LLMResponse:
        """Inner call with tenacity retry for transient network errors only.

        Tenacity behaves as follows:
        * ``httpx.HTTPError`` is retried up to 3 attempts.
        * Other exceptions (e.g. ``LLMUnavailable`` from a 4xx/5xx) propagate
          immediately without retry.
        * After 3 failed attempts the ``AsyncRetrying`` iterator re-raises the
          last ``httpx.HTTPError``, which we convert to ``LLMUnavailable``.
        """
        retrier = AsyncRetrying(
            retry=retry_if_exception_type(httpx.HTTPError),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            stop=stop_after_attempt(3),
            reraise=True,
        )
        try:
            async for attempt in retrier:
                with attempt:
                    async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                        resp = await client.post(
                            url,
                            headers={
                                "Authorization": f"Bearer {self.api_key}",
                                "Content-Type": "application/json",
                            },
                            json=body,
                        )

                    if resp.status_code != 200:
                        # Non-2xx: not a transient error — do NOT retry.
                        raise LLMUnavailable(
                            f"DeepSeek API returned {resp.status_code}: "
                            f"{resp.text[:500]}"
                        )

                    try:
                        data = resp.json()
                        text = data["choices"][0]["message"]["content"]
                        usage = data.get("usage") or {}
                    except Exception as e:
                        raise LLMUnavailable(
                            f"DeepSeek bad response shape: {e}"
                        ) from e

                    latency = int((time.monotonic() - start) * 1000)
                    return LLMResponse(
                        text=text,
                        model=self.model,
                        provider=self.name,
                        prompt_tokens=usage.get("prompt_tokens"),
                        completion_tokens=usage.get("completion_tokens"),
                        latency_ms=latency,
                    )
        except httpx.HTTPError as e:
            # All 3 retries exhausted → translate to our domain exception.
            raise LLMUnavailable(
                f"DeepSeek unreachable after 3 retries: {e}"
            ) from e

    async def health(self) -> bool:
        # Cheap probe: HEAD the base url; failure is acceptable.
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/")
                return r.status_code < 500
        except httpx.HTTPError:
            return False
