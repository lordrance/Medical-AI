from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OrderTemplate, Session


class SessionRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, session: Session) -> Session:
        self._db.add(session)
        await self._db.flush()
        return session

    async def get(self, session_id: str) -> Session | None:
        return await self._db.get(Session, session_id)

    async def all_active(self) -> list[Session]:
        result = await self._db.execute(
            select(Session).where(Session.status != "completed")
        )
        return list(result.scalars().all())

    async def count_since(self, since_dt) -> int:
        """Count sessions started since a given datetime — used for
        timeseries bucketing."""
        result = await self._db.execute(
            select(Session).where(Session.started_at >= since_dt)
        )
        return len(list(result.scalars().all()))

    async def all(self) -> list[Session]:
        result = await self._db.execute(select(Session))
        return list(result.scalars().all())

    async def all_order_templates(self) -> list[OrderTemplate]:
        result = await self._db.execute(select(OrderTemplate))
        return list(result.scalars().all())

    async def delete(self, session_id: str) -> None:
        s = await self.get(session_id)
        if s is not None:
            await self._db.delete(s)
            await self._db.flush()
