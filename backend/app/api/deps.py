"""FastAPI 的「依赖」定义。

依赖 = 接口函数执行前自动准备好的东西。写法：
    async def 某接口(db: AsyncSession = Depends(db_session)):
FastAPI 会自动调 db_session()、把数据库会话塞进 db 参数、
请求结束后自动清理。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db


async def db_session() -> AsyncIterator[AsyncSession]:
    """给当前请求发一个数据库会话。

    只是对 db/session.py 里 get_db() 的一层转发。多这一层是为了让
    所有接口都从 app.api.deps 导入依赖，将来要给依赖加逻辑
    （比如按请求打点、多数据库路由）只改这一个地方。
    """
    async for s in get_db():
        yield s
