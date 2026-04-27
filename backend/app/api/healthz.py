from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter()


@router.get("/healthz", tags=["meta"])
async def healthz() -> dict:
    settings = get_settings()
    return {
        "ok": True,
        "appName": settings.APP_NAME,
        "appVersion": settings.APP_VERSION,
        "env": settings.APP_ENV,
        "llmProvider": settings.LLM_PROVIDER,
        "llmEnabled": settings.llm_enabled,
    }
