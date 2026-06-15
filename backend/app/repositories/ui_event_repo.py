from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UiEvent


class UiEventRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, event: UiEvent) -> UiEvent:
        self._db.add(event)
        await self._db.flush()
        return event

    async def by_session(self, session_id: str) -> list[UiEvent]:
        result = await self._db.execute(
            select(UiEvent).where(UiEvent.session_id == session_id)
        )
        return list(result.scalars().all())

    async def latest_by_session(self, session_id: str) -> UiEvent | None:
        result = await self._db.execute(
            select(UiEvent)
            .where(UiEvent.session_id == session_id)
            .order_by(UiEvent.server_ts.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def latest_per_session(self, session_ids: list[str]) -> dict[str, UiEvent]:
        """For each session_id, return the most-recent UiEvent (or absent key
        if that session has no events). Uses a single query + client dedup."""
        if not session_ids:
            return {}
        result = await self._db.execute(
            select(UiEvent)
            .where(UiEvent.session_id.in_(session_ids))
            .order_by(UiEvent.server_ts.desc())
        )
        seen: dict[str, UiEvent] = {}
        for ev in result.scalars():
            if ev.session_id not in seen:
                seen[ev.session_id] = ev
        return seen

    async def all(self) -> list[UiEvent]:
        result = await self._db.execute(select(UiEvent))
        return list(result.scalars().all())

    async def delete_by_session(self, session_id: str) -> None:
        for ev in await self.by_session(session_id):
            await self._db.delete(ev)
        await self._db.flush()
