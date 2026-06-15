"""Global exception handlers that wrap every error response with
request_id, timestamp, and type fields for structured error reporting.

Usage:
    from app.core.exception_handlers import register_exception_handlers
    register_exception_handlers(app)
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = structlog.get_logger(__name__)


def _get_request_id(request: Request) -> str:
    import structlog.contextvars

    ctx = structlog.contextvars.get_contextvars()
    return ctx.get("request_id") or request.headers.get("X-Request-ID", "unknown")


def register_exception_handlers(app: FastAPI) -> None:
    """Register all structured exception handlers on the FastAPI app."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        rid = _get_request_id(request)
        logger.warning(
            "http_exception",
            status_code=exc.status_code,
            detail=exc.detail,
            request_id=rid,
            path=str(request.url),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "request_id": rid,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "http_error",
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        rid = _get_request_id(request)
        errors = [
            {
                "field": " -> ".join(str(loc) for loc in err.get("loc", [])),
                "message": err.get("msg", ""),
            }
            for err in exc.errors()
        ]
        logger.warning(
            "validation_error",
            errors=errors,
            request_id=rid,
            path=str(request.url),
        )
        return JSONResponse(
            status_code=422,
            content={
                "detail": errors,
                "request_id": rid,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "validation_error",
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        rid = _get_request_id(request)
        logger.error(
            "internal_error",
            exc_info=exc,
            request_id=rid,
            path=str(request.url),
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "request_id": rid,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "internal_error",
            },
        )
