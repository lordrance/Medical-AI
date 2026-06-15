from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta, timezone, datetime

from app.db.models import LLMCall


class LLMCallRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, call: LLMCall) -> LLMCall:
        self._db.add(call)
        await self._db.flush()
        return call

    async def all(self) -> list[LLMCall]:
        result = await self._db.execute(select(LLMCall))
        return list(result.scalars().all())

    async def recent_24h(self) -> list[LLMCall]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await self._db.execute(
            select(LLMCall).where(LLMCall.created_at >= cutoff)
        )
        return list(result.scalars().all())
