"""FastAPI middleware that injects a `request_id` into every request.

Adds a `request_id` key to structlog's thread-local context before the
request handler runs, and appends `X-Request-ID` to the response. If the
caller already sent an `X-Request-ID` header we reuse it (trace
propagation); otherwise we generate a short unique id.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)

_REQUEST_ID_HEADER = "X-Request-ID"


def _short_id() -> str:
    """8-char hex — short enough for logs, unique enough for a study."""
    return uuid.uuid4().hex[:8]


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:  # type: ignore[valid-type]
        rid = request.headers.get(_REQUEST_ID_HEADER) or _short_id()

        # Bind into structlog so every log call in this request carries the id.
        structlog.contextvars.bind_contextvars(request_id=rid)

        response = await call_next(request)
        response.headers[_REQUEST_ID_HEADER] = rid

        # Unbind once the request is done so ids don't leak across requests.
        structlog.contextvars.unbind_contextvars("request_id")
        return response
