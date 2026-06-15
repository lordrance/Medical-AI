from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CaseSurvey, PostSurvey


class SurveyRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_case_survey(self, survey: CaseSurvey) -> CaseSurvey:
        self._db.add(survey)
        await self._db.flush()
        return survey

    async def create_post_survey(self, survey: PostSurvey) -> PostSurvey:
        self._db.add(survey)
        await self._db.flush()
        return survey

    async def get_post_survey(self, participant_id: str) -> PostSurvey | None:
        result = await self._db.execute(
            select(PostSurvey).where(PostSurvey.participant_id == participant_id)
        )
        return result.scalars().first()

    async def all_post_surveys(self) -> list[PostSurvey]:
        result = await self._db.execute(select(PostSurvey))
        return list(result.scalars().all())

    async def all_case_surveys(self) -> list[CaseSurvey]:
        result = await self._db.execute(select(CaseSurvey))
        return list(result.scalars().all())

    async def delete_by_participant(self, participant_id: str) -> None:
        ps = await self.get_post_survey(participant_id)
        if ps is not None:
            await self._db.delete(ps)
            await self._db.flush()

    async def delete_case_survey_by_presentation(self, pres_id: str) -> None:
        result = await self._db.execute(
            select(CaseSurvey).where(CaseSurvey.case_presentation_id == pres_id)
        )
        cs = result.scalars().first()
        if cs is not None:
            await self._db.delete(cs)
            await self._db.flush()
