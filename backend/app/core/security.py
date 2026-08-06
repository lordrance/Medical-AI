"""
================================================================================
文件作用：管理员鉴权 —— 全站唯一的权限检查
================================================================================

所有 /api/admin/* 的接口都靠这个文件挡住外人。医生端的接口不需要它
（那些接口靠 sessionId 认人就够了，而 sessionId 本身就是不可猜的随机串）。

安全模型很简单：一个共享口令（ADMIN_TOKEN），对上了就是管理员。
对一个只跑几周、只有一位管理员的研究平台来说，这个强度是够的。

--------------------------------------------------------------------------------
★ 口令的两条传递方式，以及为什么前端只用其中一条
--------------------------------------------------------------------------------
  请求头 X-Admin-Token   ← 前端一律用这条
  网址参数 ?token=xxx    ← 只是为了让你用 curl 或浏览器直接下载文件时方便

  网址里带口令的问题：会留在浏览器历史里、会通过 Referer 头泄露给第三方、
  截图时会连口令一起截进去。所以后台前端把口令存在 sessionStorage，
  下载文件也走 downloadWithToken()（fetch + Blob 合成下载），
  保证口令只出现在请求头里。

--------------------------------------------------------------------------------
本文件的代码块：
--------------------------------------------------------------------------------
  第 1 块  require_admin()   唯一的一个函数：校验令牌，不对就拦下
================================================================================
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.core.config import get_settings


# ── 第 1 块：校验管理员令牌 ────────────────────────────────────────────────
def require_admin(request: Request) -> None:
    """Validate admin token from `X-Admin-Token` header or `?token=` query.

    Raise 401 / 500 accordingly.

    中文：用法是在接口函数里直接调一下：

        @router.get("/summary")
        async def get_summary(request: Request, ...):
            require_admin(request)      # ← 这一行
            ...

    校验不过会直接抛异常，后面的代码根本不会执行。
    ★ 新加 admin 接口时千万别忘了这一行——漏了就等于把研究数据公开给全世界。
    """
    settings = get_settings()
    expected = settings.ADMIN_TOKEN

    # ---- 情况 1：服务器压根没配口令 ----
    if not expected:
        # ★ 这时必须报 500 拒绝服务，绝不能"没配就放行"。
        #   "没配置就不检查"是一种很常见也很致命的写法：
        #   部署时忘了注入环境变量，后台就对全世界敞开了，而且毫无征兆。
        #   宁可服务不可用，也不能默默地把数据暴露出去。
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ADMIN_TOKEN not configured on server",
        )

    # ---- 情况 2：从请求里把令牌取出来 ----
    # 请求头的名字用小写：HTTP 头名不区分大小写，FastAPI 内部统一存成小写，
    # 所以这里必须写 "x-admin-token" 才取得到。
    # `or` 表示"请求头里没有就退而求其次看网址参数"。
    token = request.headers.get("x-admin-token") or request.query_params.get("token")

    # ---- 情况 3：比对 ----
    if token != expected:
        # 401 = "你没有权限"。
        # ★ 提示信息只说 "Unauthorized"，不说"口令错了"还是"没带口令"——
        #   区分得越细，越方便别人试探。
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
    # 走到这里说明验证通过，函数正常返回 None，调用方继续往下执行。
