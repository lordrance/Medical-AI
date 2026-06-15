from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Case


class CaseRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, case_id: str) -> Case | None:
        return await self._db.get(Case, case_id)

    async def get_practice(self) -> Case | None:
        result = await self._db.execute(
            select(Case).where(Case.is_practice.is_(True))
        )
        return result.scalars().first()

    async def all_formal(self) -> list[Case]:
        result = await self._db.execute(
            select(Case).where(Case.is_practice.is_(False))
        )
        return list(result.scalars().all())

    async def all(self) -> list[Case]:
        result = await self._db.execute(select(Case))
        return list(result.scalars().all())
