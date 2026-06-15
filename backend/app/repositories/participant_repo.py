from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Participant


class ParticipantRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, participant: Participant) -> Participant:
        self._db.add(participant)
        await self._db.flush()
        return participant

    async def get(self, participant_id: str) -> Participant | None:
        return await self._db.get(Participant, participant_id)

    async def count_total(self) -> int:
        result = await self._db.execute(select(func.count(Participant.id)))
        return result.scalar() or 0

    async def count_completed(self) -> int:
        result = await self._db.execute(
            select(func.count(Participant.id)).where(
                Participant.completed_flag.is_(True)
            )
        )
        return result.scalar() or 0

    async def all(self) -> list[Participant]:
        result = await self._db.execute(select(Participant))
        return list(result.scalars().all())

    async def condition_counts(self) -> list[tuple[str, int]]:
        result = await self._db.execute(
            select(Participant.condition, func.count(Participant.id)).group_by(
                Participant.condition
            )
        )
        return [(r[0], int(r[1])) for r in result.all()]

    async def delete_by_id(self, participant_id: str) -> None:
        p = await self.get(participant_id)
        if p is not None:
            await self._db.delete(p)
            await self._db.flush()
