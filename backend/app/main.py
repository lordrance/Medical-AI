"""
================================================================================
文件作用：★ 后端的总装配 —— 整个 FastAPI 应用在这里拼起来
================================================================================

gunicorn 启动时加载的就是这个文件（命令行里那句 "app.main:app"）。
它自己不处理任何业务，只负责把各个零件装到一起：

  1. 装中间件      给每个请求发一个追踪编号
  2. 装异常处理器  把各种错误统一成一种 JSON 格式
  3. 装 CORS       允许前端跨域访问
  4. 注册路由      把所有接口挂上去

--------------------------------------------------------------------------------
本文件的代码块（从上到下）：
--------------------------------------------------------------------------------
  第 1 块  _logger / _REQUEST_ID_RE  日志器和一个正则
  第 2 块  _setup_logging()          配置日志格式
  第 3 块  lifespan()                启动和关闭时各做一件事
  第 4 块  create_app()              ★ 装配函数，下面 5 小块都在它里面
      4a  请求编号中间件
      4b  三个异常处理器
      4c  CORS
      4d  注册全部路由
  第 5 块  app = create_app()        真正被 gunicorn 加载的那个对象
================================================================================
"""

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

# ── 第 1 块：日志器和正则 ────────────────────────────────────────────────
# 全项目的主日志器。给它起个固定名字，方便在日志里筛。
_logger = logging.getLogger("medical-ai")
# 校验前端自带的追踪编号：只允许字母数字和横杠，最长 64 个字符。
# ★ 这个限制是安全措施，原因见第 4a 块。
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")


# ── 第 2 块：日志格式 ────────────────────────────────────────────────────
def _setup_logging() -> None:
    """配置日志的输出格式。

    level=INFO 表示 INFO 及以上级别都打印（DEBUG 不打）。
    格式里带时间、级别、来源，方便 `docker logs` 时快速定位。
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


# ── 第 3 块：启动 / 关闭钩子 ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用启动时跑 yield 之前的，关闭时跑 yield 之后的。

    这里只打两条日志。看 `docker logs` 时，出现 backend_starting
    就说明这个进程起来了；4 个 gunicorn 进程会各打一条。
    """
    _setup_logging()
    _logger.info("backend_starting", extra={"version": get_settings().APP_VERSION})
    yield
    _logger.info("backend_shutting_down")


# ── 第 4 块：装配函数 ★ ──────────────────────────────────────────────────
def create_app() -> FastAPI:
    """把所有零件装到一起，返回一个可以运行的应用对象。

    ★ 为什么写成函数而不是直接在文件里一行行写：
      测试需要能造出一个干净的应用实例。写成函数就能随时再造一个。
    """
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

    # ---- 4a：请求编号中间件 ----
    # --- Request-ID middleware (inlined for V4 hotfix — no new file) ---
    #
    # ★ 中文：给每个请求发一个 8 位追踪 ID，同时写进日志和返回给前端。
    # 这样医生反馈「我这里报错了」时，让他截图，图里的 request_id
    # 就能在服务器日志里精确定位到那一次请求的完整堆栈。
    def _clean_request_id(raw: str | None) -> str:
        # Accept a client-supplied X-Request-ID only if it's a short, safe
        # token; otherwise mint a fresh one. Prevents log forging / oversized
        # values from an untrusted header flowing into log lines.
        #
        # 中文：如果前端自己带了 ID，只在它「短且只含安全字符」时才采信。
        # 否则别人可以在这个头里塞换行符来伪造日志行，或者塞几 MB 文本把
        # 日志撑爆。不合规就自己生成一个。
        if raw and _REQUEST_ID_RE.match(raw):
            return raw
        return uuid.uuid4().hex[:8]

    @app.middleware("http")
    async def _request_id_middleware(request: Request, call_next):
        """中间件 = 每个请求进出都要经过的一层。"""
        rid = _clean_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = rid   # 挂到请求上，后面的异常处理器要读
        response = await call_next(request)  # ← 真正的接口处理在这一行里发生
        response.headers["X-Request-ID"] = rid  # 回传给前端
        return response

    # ---- 4b：三个异常处理器 ----
    # --- Structured error handlers ---
    #
    # ★ 中文：三个异常处理器，把所有错误统一成
    # {detail, request_id, timestamp} 这一种 JSON 格式。
    # 好处：前端只用写一套解析逻辑；每个错误都带追踪 ID 方便排查。

    @app.exception_handler(HTTPException)
    async def _http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        """处理我们主动抛的错（404 会话不存在、401 未授权等）。
        这些是「预期内」的错误，记 warning 就够了。"""
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
        """处理「前端传的数据不合规」（422）。

        ★ 这里必须手工拍平错误信息：Pydantic 的报错对象里塞了 Python
        异常实例，不能转成 JSON。直接返回会让 FastAPI 渲染响应时自己崩掉，
        结果医生看到 500「网络异常」而不是「有题目没答对」。
        （survey.py 里也有一份同样的处理，因为那里是手动 catch 的。）
        """
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
        """★ 兜底：处理所有没预料到的异常（代码 bug、数据库炸了…）。

        对外只说 "Internal server error"，**绝不回传异常内容**——
        堆栈里可能有数据库连接串、文件路径等敏感信息。
        完整堆栈只写进服务器日志（exc_info=True）。
        """
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

    # CORS：允许哪些网站的网页调用这个 API。
    # 生产环境前后端同域（都在 medraftlab.com 下，由 Caddy 分流），
    # 所以其实用不上 CORS；配置留着是为了本地开发时前端在 :3000、
    # 后端在 :8000，属于跨域。
    # ---- 4c：CORS ----
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- 注册所有接口路由 ----
    # 每个 router 自带前缀，具体路径见各文件顶部。
    # ---- 4d：注册全部路由 ----
    app.include_router(healthz.router)          # /healthz          健康检查
    app.include_router(session_api.router)      # /api/session      建档
    app.include_router(case.router)             # /api/case/*       发题
    app.include_router(survey.router)           # /api/pre|post-survey
    app.include_router(action.router)           # /api/action       ★提交作答
    app.include_router(ui_event.router)         # /api/ui-event     埋点
    app.include_router(voice_recording.router)  # /api/voice-recording（V4 前端已停用）
    # 以下都是 /api/admin/*，需要管理员 token
    app.include_router(admin_summary.router)    # 汇总统计
    app.include_router(admin_export.router)     # 数据导出
    app.include_router(admin_llm.router)        # AI 生成研究总结
    app.include_router(admin_dashboard.router)  # 看板数据

    return app


# ── 第 5 块：应用对象 ────────────────────────────────────────────────────
# gunicorn 启动时加载的就是这个变量（命令行里的 "app.main:app"）。
# 模块被导入时这一行就会执行，把整个应用装配好。
app = create_app()
