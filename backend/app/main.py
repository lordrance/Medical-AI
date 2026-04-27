from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import action, case, healthz, session as session_api, survey, ui_event
from app.api.admin import export as admin_export, summary as admin_summary
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


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
    app.include_router(admin_summary.router)
    app.include_router(admin_export.router)

    return app


app = create_app()
