from __future__ import annotations

import logging
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from app.api import (
    action,
    case,
    healthz,
    session as session_api,
    survey,
    ui_event,
    voice_recording,
)
from app.api.admin import (
    dashboard as admin_dashboard,
    export as admin_export,
    llm as admin_llm,
    summary as admin_summary,
)
from app.core.config import get_settings

_logger = logging.getLogger("medical-ai")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _setup_logging()
    _logger.info("backend_starting", extra={"version": get_settings().APP_VERSION})
    yield
    _logger.info("backend_shutting_down")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Medical AI Draft Review – API",
        description=(
            "FastAPI backend for the medical AI draft review HCI study platform.\n\n"
            "中文: 医生端 AI 草稿审核模拟平台后端 API。"
        ),
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    # --- Request-ID middleware (inlined for V4 hotfix — no new file) ---
    def _clean_request_id(raw: str | None) -> str:
        # Accept a client-supplied X-Request-ID only if it's a short, safe
        # token; otherwise mint a fresh one. Prevents log forging / oversized
        # values from an untrusted header flowing into log lines.
        if raw and _REQUEST_ID_RE.match(raw):
            return raw
        return uuid.uuid4().hex[:8]

    @app.middleware("http")
    async def _request_id_middleware(request: Request, call_next):
        rid = _clean_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

    # --- Structured error handlers ---
    @app.exception_handler(HTTPException)
    async def _http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        rid = getattr(request.state, "request_id", "unknown")
        _logger.warning(
            "http_exception status=%d path=%s request_id=%s detail=%s",
            exc.status_code, request.url.path, rid, exc.detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "request_id": rid,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        rid = getattr(request.state, "request_id", "unknown")
        safe_errors = [
            {
                "field": " -> ".join(str(loc) for loc in e.get("loc", [])),
                "message": e.get("msg", ""),
            }
            for e in exc.errors()
        ]
        _logger.warning(
            "validation_error path=%s request_id=%s errors=%s",
            request.url.path, rid, len(safe_errors),
        )
        return JSONResponse(
            status_code=422,
            content={
                "detail": safe_errors,
                "request_id": rid,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    @app.exception_handler(Exception)
    async def _general_error(request: Request, exc: Exception) -> JSONResponse:
        rid = getattr(request.state, "request_id", "unknown")
        _logger.error(
            "internal_error path=%s request_id=%s error=%s",
            request.url.path, rid, repr(exc),
            exc_info=True,
        )
        # ServerErrorMiddleware runs outside the request-id middleware, so the
        # X-Request-ID response header would otherwise be missing on 500s.
        # Set it directly here so clients can still correlate the failure.
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "request_id": rid,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            headers={"X-Request-ID": rid},
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(healthz.router)
    app.include_router(session_api.router)
    app.include_router(case.router)
    app.include_router(survey.router)
    app.include_router(action.router)
    app.include_router(ui_event.router)
    app.include_router(voice_recording.router)
    app.include_router(admin_summary.router)
    app.include_router(admin_export.router)
    app.include_router(admin_llm.router)
    app.include_router(admin_dashboard.router)

    return app


app = create_app()
