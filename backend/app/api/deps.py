from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db


async def db_session() -> AsyncIterator[AsyncSession]:
    async for s in get_db():
        yield s


DBSession = Depends(db_session)
