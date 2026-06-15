"""Global FastAPI exception handlers.

Registers structured JSON error response handlers for HTTPException,
RequestValidationError, and generic Exception. Every response includes
request_id, timestamp, and type fields for observability.
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
import structlog.contextvars
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = structlog.get_logger(__name__)


def _get_request_id(request: Request) -> str:
    ctx = structlog.contextvars.get_contextvars()
    rid = ctx.get("request_id")
    if rid:
        return rid
    return request.headers.get("X-Request-ID", "unknown")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "request_id": _get_request_id(request),
            "timestamp": _timestamp(),
            "type": "http_error",
        },
    )


def _sanitize_errors(errors: list[dict]) -> list[dict]:
    """Recursively stringify non-serializable objects (e.g. ValueError) in Pydantic error dicts."""
    result: list[dict] = []
    for err in errors:
        sanitized: dict = {}
        for k, v in err.items():
            if isinstance(v, dict):
                sanitized[k] = {kk: str(vv) if not isinstance(vv, (str, int, float, bool, list, dict, type(None))) else vv for kk, vv in v.items()}
            elif not isinstance(v, (str, int, float, bool, list, dict, type(None))):
                sanitized[k] = str(v)
            else:
                sanitized[k] = v
        result.append(sanitized)
    return result


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": _sanitize_errors(exc.errors()),
            "request_id": _get_request_id(request),
            "timestamp": _timestamp(),
            "type": "validation_error",
        },
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    rid = _get_request_id(request)
    logger.error(
        "unhandled_exception",
        exc_info=exc,
        path=str(request.url),
        request_id=rid,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "request_id": rid,
            "timestamp": _timestamp(),
            "type": "internal_error",
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all custom exception handlers on the FastAPI application."""
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
