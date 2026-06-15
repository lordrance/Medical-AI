from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.llm.base import LLMResponse, LLMUnavailable
from app.llm.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

logger = logging.getLogger(__name__)

# Module-level circuit breaker shared across all DeepseekProvider instances.
_circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=300.0)


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(3),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _http_post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    json: dict[str, Any],
) -> httpx.Response:
    """Issue an HTTP POST and retry on network errors only."""
    return await client.post(url, headers=headers, json=json)


async def _audit_circuit_open(
    provider_name: str,
    model: str,
    prompt_text: str,
    error_msg: str,
) -> None:
    """Write a circuit-open event to the llm_calls audit table.

    Creates its own DB session so it can be called from anywhere.
    Silently swallows DB errors so a failing audit never breaks the caller.
    """
    try:
        from app.db.models import LLMCall
        from app.db.session import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            session.add(
                LLMCall(
                    purpose="circuit_open",
                    provider=provider_name,
                    model=model,
                    prompt_text=prompt_text[:4000],
                    response_text="",
                    prompt_tokens=None,
                    completion_tokens=None,
                    latency_ms=0,
                    error=error_msg,
                )
            )
            await session.commit()
    except Exception:
        logger.exception("Failed to audit circuit-open event; silently ignored.")


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

        # The HTTP call is wrapped in circuit breaker (outer) + tenacity retry (inner).
        # Circuit breaker catches all exceptions from the retried call.
        try:
            resp = await _circuit_breaker.call(
                lambda: self._do_http_post(url, body)
            )
        except CircuitBreakerOpenError as e:
            # Circuit is OPEN — reject immediately and log to audit.
            logger.warning("LLM call rejected by circuit breaker: %s", e)
            await _audit_circuit_open(
                provider_name=self.name,
                model=self.model,
                prompt_text=user[:4000],
                error_msg=str(e),
            )
            raise LLMUnavailable(
                "LLM temporarily unavailable: circuit breaker is OPEN"
            ) from e
        except Exception as e:
            # Network errors (httpx.HTTPError) that survived tenacity retries,
            # or any other unexpected error from the HTTP call, must be wrapped
            # in LLMUnavailable so callers always catch a consistent exception.
            raise LLMUnavailable(f"DeepSeek HTTP error: {e}") from e

        if resp.status_code != 200:
            raise LLMUnavailable(
                f"DeepSeek API returned {resp.status_code}: {resp.text[:500]}"
            )
        try:
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
        except Exception as e:
            raise LLMUnavailable(f"DeepSeek bad response shape: {e}") from e

        latency = int((time.monotonic() - start) * 1000)
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.name,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            latency_ms=latency,
        )

    async def _do_http_post(
        self,
        url: str,
        body: dict[str, Any],
    ) -> httpx.Response:
        """Perform the actual HTTP POST with tenacity retry.

        This method is wrapped by the circuit breaker in ``generate()``.
        """
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            return await _http_post_with_retry(
                client,
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )

    async def health(self) -> bool:
        # Cheap probe: HEAD the base url; failure is acceptable.
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/")
                return r.status_code < 500
        except httpx.HTTPError:
            return False
