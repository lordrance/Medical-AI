"""管理员鉴权。

★ 全站唯一的权限检查。所有 /api/admin/* 接口都靠它挡住外人。
医生端的接口不需要鉴权（靠 sessionId 认人就够了）。

安全模型很简单：一个共享密钥 ADMIN_TOKEN，对上了就是管理员。
对一个只跑几周、只有你一个管理员的研究平台来说，这个强度是够的。
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.core.config import get_settings


def require_admin(request: Request) -> None:
    """Validate admin token from `X-Admin-Token` header or `?token=` query.

    Raise 401 / 500 accordingly.

    中文：校验管理员令牌。用法是挂在接口上当依赖：
        @router.get("/xxx", dependencies=[Depends(require_admin)])
    校验不过会直接抛异常，请求根本进不到接口函数里。
    """
    settings = get_settings()
    expected = settings.ADMIN_TOKEN
    if not expected:
        # 服务器压根没配 token = 部署事故。这时候必须报 500 拒绝服务，
        # 绝不能「没配就放行」——那等于后台对全世界敞开。
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ADMIN_TOKEN not configured on server",
        )

    # 两种传法都接受：
    #   请求头 X-Admin-Token  ← ★ 前端一律用这种
    #   网址参数 ?token=xxx   ← 只为了让你用 curl / 浏览器直接下载文件时方便
    #
    # ★ 安全提醒：token 放进网址会泄露到浏览器历史、Referer 头、截图里。
    # 所以后台前端把 token 存在 sessionStorage，下载文件也走
    # downloadWithToken()（fetch + Blob），保证 token 只走请求头。
    token = request.headers.get("x-admin-token") or request.query_params.get("token")
    if token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
