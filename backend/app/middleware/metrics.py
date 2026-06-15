"""Pure ASGI middleware that records HTTP request metrics to a daily JSONL file.

Every request (except ``/healthz``) is logged as a JSON line in
``logs/metrics-YYYY-MM-DD.jsonl`` under the project root, with the fields:

- ``method``      — HTTP method (GET, POST, …)
- ``path``        — URL path
- ``statusCode``  — response status code
- ``durationMs``  — wall-clock duration in milliseconds
- ``requestId``   — ``X-Request-ID`` from the response headers (filled by
                    ``RequestIdMiddleware``, which must run before this one)

The middleware is a pure ASGI callable (not ``BaseHTTPMiddleware``) to avoid
the overhead of Starlette's request parsing for observability-only code and to
guarantee that the ``finally`` block runs even when downstream handlers raise.
"""

from __future__ import annotations

import os
import time
from collections.abc import Awaitable, Callable
from datetime import date

import structlog

try:
    import orjson
except ImportError:  # pragma: no cover
    orjson = None  # type: ignore[assignment]

logger = structlog.get_logger(__name__)

_LOGS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs"
)
_EXCLUDED_PATHS = frozenset({"/healthz"})


def _today_path() -> str:
    """Return the absolute path to today's metrics file."""
    os.makedirs(_LOGS_DIR, exist_ok=True)
    return os.path.join(_LOGS_DIR, f"metrics-{date.today().isoformat()}.jsonl")


def _p95(values: list[float]) -> float:
    """P95 of *values*, or 0 when empty."""
    if not values:
        return 0.0
    s = sorted(values)
    return s[int(len(s) * 0.95)]


def _read_metrics(
    path: str, cutoff: float
) -> tuple[int, int, list[float]]:
    """Return ``(total_requests, error_count, latencies)`` from a JSONL file.

    *cutoff* is a ``time.time()`` epoch that filters rows whose ``timestamp``
    field is older than the cutoff. Rows with no ``timestamp`` are included.
    """
    total = 0
    errors = 0
    latencies: list[float] = []
    try:
        with open(path, "rb") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = orjson.loads(line)
                except Exception:
                    continue

                ts = row.get("timestamp")
                if ts is not None and ts < cutoff:
                    continue

                total += 1
                sc = row.get("statusCode", 0)
                if sc < 200 or sc >= 300:
                    errors += 1
                dur = row.get("durationMs")
                if dur is not None:
                    latencies.append(float(dur))
    except FileNotFoundError:
        pass
    return total, errors, latencies


class MetricsMiddleware:
    """ASGI middleware — records HTTP metrics, excludes ``/healthz``."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self, scope: dict, receive: Callable[..., Awaitable[None]],
        send: Callable[..., Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in _EXCLUDED_PATHS:
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        status_code = 0

        async def _send(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            elapsed_ms = (time.monotonic() - start) * 1000
            method = scope.get("method", "")
            request_id = ""
            # Grab request_id from structlog context (set by RequestIdMiddleware)
            ctx = structlog.contextvars.get_contextvars()
            if ctx:
                request_id = str(ctx.get("request_id", ""))

            try:
                record = orjson.dumps({
                    "timestamp": time.time(),
                    "method": method,
                    "path": path,
                    "statusCode": status_code,
                    "durationMs": round(elapsed_ms, 2),
                    "requestId": request_id,
                })
                with open(_today_path(), "ab") as f:
                    f.write(record + b"\n")
            except Exception:
                logger.exception("Failed to write metrics record")


def get_recent_metrics(lookback_seconds: int = 3600) -> dict:
    """Aggregate metrics from JSONL files within the given lookback window.

    Returns a dict with keys:
    - ``errorRate``       — float 0.0–1.0 (0 when no requests)
    - ``p95LatencyMs``    — P95 latency in ms (0 when no latencies)
    - ``totalRequests``   — integer count
    """
    cutoff = time.time() - lookback_seconds
    total_requests = 0
    total_errors = 0
    all_latencies: list[float] = []

    metrics_dir = _LOGS_DIR
    if not os.path.isdir(metrics_dir):
        return {"errorRate": 0.0, "p95LatencyMs": 0.0, "totalRequests": 0}

    for fname in os.listdir(metrics_dir):
        if not fname.startswith("metrics-") or not fname.endswith(".jsonl"):
            continue
        p = os.path.join(metrics_dir, fname)
        if not os.path.isfile(p):
            continue
        t, e, lats = _read_metrics(p, cutoff)
        total_requests += t
        total_errors += e
        all_latencies.extend(lats)

    return {
        "errorRate": round(total_errors / total_requests, 4)
        if total_requests > 0 else 0.0,
        "p95LatencyMs": round(_p95(all_latencies), 2),
        "totalRequests": total_requests,
    }
