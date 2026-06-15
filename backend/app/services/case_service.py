"""Business logic for case rendering and presentation lifecycle."""

from __future__ import annotations
import uuid
from datetime import datetime, timezone

from app.repositories.case_repo import CaseRepo
from app.repositories.session_repo import SessionRepo
from app.repositories.action_repo import ActionRepo
from app.db.models import CasePresentation, Action


class CaseService:
    def __init__(self, case_repo: CaseRepo, session_repo: SessionRepo,
                 action_repo: ActionRepo) -> None:
        self._crepo = case_repo
        self._srepo = session_repo
        self._arepo = action_repo

    async def get_case_for_participant(self, case_id: str, session_id: str) -> dict:
        """Return case payload for rendering. V4/V5 always returns the
        seeded ai_draft verbatim — no LLM call."""
        case = await self._crepo.get(case_id)
        if case is None:
            raise ValueError("Case not found")
        return {
            "id": case.id, "isPractice": case.is_practice,
            "riskLevel": case.risk_level,
            "patientMessage": case.patient_message,
            "chartSnapshot": case.chart_snapshot,
            "aiDraft": case.ai_draft,
            "guardrail": None,  # V4 single-condition study
        }

    async def open_case_presentation(self, session_id: str, case_id: str,
                                      order_index: int) -> str:
        """Create or reuse an in-progress CasePresentation.
        Returns the presentation id."""
        db = self._arepo._db
        from sqlalchemy import select
        reuse_stmt = (
            select(CasePresentation)
            .outerjoin(Action, Action.case_presentation_id == CasePresentation.id)
            .where(CasePresentation.session_id == session_id,
                   CasePresentation.case_id == case_id,
                   Action.id.is_(None))
            .order_by(CasePresentation.started_at.asc()).limit(1)
        )
        existing = (await db.execute(reuse_stmt)).scalars().first()
        if existing is not None:
            existing.order_index = order_index
            await db.commit()
            return existing.id

        pres = CasePresentation(id=uuid.uuid4().hex, session_id=session_id,
                                case_id=case_id, order_index=order_index,
                                started_at=datetime.now(timezone.utc))
        db.add(pres)
        await db.commit()
        await db.refresh(pres)
        return pres.id
