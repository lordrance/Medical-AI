"""Business logic for survey submission (pre/post + case embedded)."""

from __future__ import annotations
import uuid
from app.repositories.survey_repo import SurveyRepo
from app.db.models import PostSurvey, CaseSurvey, UiEvent


class SurveyService:
    def __init__(self, survey_repo: SurveyRepo) -> None:
        self._srepo = survey_repo

    async def submit_case_survey(self, pres_id: str, confidence: int,
                                 helpfulness: int) -> CaseSurvey:
        cs = CaseSurvey(id=uuid.uuid4().hex, case_presentation_id=pres_id,
                        case_decision_confidence=confidence,
                        case_draft_helpfulness=helpfulness)
        return await self._srepo.create_case_survey(cs)

    async def submit_post_survey(self, *, participant_id: str, session_id: str,
                                  payload: dict) -> PostSurvey:
        ps = PostSurvey(id=uuid.uuid4().hex, participant_id=participant_id,
                        session_id=session_id, payload=payload)
        return await self._srepo.create_post_survey(ps)
