"""健康检查接口。

★ 打开 https://medraftlab.com/healthz 看到 {"ok":true,...} 就说明后端活着。
出问题时这是你第一个该看的地方。

三个地方会调它：
  1. Docker 的 healthcheck（每 30 秒一次，连续失败会标记容器不健康）
  2. Caddy 的转发规则里单独放行了这个路径
  3. 你自己排查问题时

★ 故意不需要鉴权：它只返回版本号和配置开关，不含任何数据。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter()


@router.get("/healthz", tags=["meta"])
async def healthz() -> dict:
    """GET /healthz

    注意它**不查数据库**。这是有意的：数据库慢的时候，健康检查还应该
    快速返回，否则 Docker 会误判容器已死并把它重启，反而雪上加霜。
    """
    settings = get_settings()
    return {
        "ok": True,
        "appName": settings.APP_NAME,
        "appVersion": settings.APP_VERSION,
        "env": settings.APP_ENV,
        "llmProvider": settings.LLM_PROVIDER,
        "llmEnabled": settings.llm_enabled,
    }
