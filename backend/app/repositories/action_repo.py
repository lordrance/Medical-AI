from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Action, CasePresentation


class ActionRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, action: Action) -> Action:
        self._db.add(action)
        await self._db.flush()
        return action

    async def get_by_presentation(self, pres_id: str) -> Action | None:
        result = await self._db.execute(
            select(Action).where(Action.case_presentation_id == pres_id)
        )
        return result.scalars().first()

    async def all_with_presentation(self) -> list[Action]:
        result = await self._db.execute(
            select(Action).options(
                selectinload(Action.presentation)
                .selectinload(CasePresentation.case),
                selectinload(Action.presentation)
                .selectinload(CasePresentation.session),
            )
        )
        return list(result.scalars().all())

    async def delete_by_presentation(self, pres_id: str) -> None:
        a = await self.get_by_presentation(pres_id)
        if a is not None:
            await self._db.delete(a)
            await self._db.flush()
