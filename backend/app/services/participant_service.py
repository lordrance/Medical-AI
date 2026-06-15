"""Business logic for participant lifecycle."""

from __future__ import annotations
import uuid
from datetime import datetime, timezone

from app.db.models import Participant, Session, UiEvent
from app.repositories.participant_repo import ParticipantRepo
from app.repositories.session_repo import SessionRepo
from app.repositories.ui_event_repo import UiEventRepo
from app.services.randomization import pick_order_template_id

SINGLE_CONDITION = "single"

class ParticipantService:
    def __init__(self, participant_repo: ParticipantRepo, session_repo: SessionRepo,
                 ui_event_repo: UiEventRepo) -> None:
        self._prepo = participant_repo
        self._srepo = session_repo
        self._urepo = ui_event_repo

    async def create_session(self) -> dict:
        templates = await self._srepo.all_order_templates()
        if not templates:
            raise ValueError("No order templates seeded")
        tpl_id = pick_order_template_id([t.id for t in templates])
        tpl = next(t for t in templates if t.id == tpl_id)

        # Find practice case — delegated to CaseRepo caller or direct import
        from app.db.models import Case
        from app.repositories.case_repo import CaseRepo
        case_repo = CaseRepo(self._prepo._db)
        practice = await case_repo.get_practice()

        p = Participant(id=uuid.uuid4().hex, condition=SINGLE_CONDITION, order_template_id=tpl_id)
        await self._prepo.create(p)
        s = Session(id=uuid.uuid4().hex, participant_id=p.id, status="active")
        await self._srepo.create(s)
        await self._urepo.create(UiEvent(
            id=uuid.uuid4().hex, session_id=s.id, event_type="session_started",
            payload={"condition": SINGLE_CONDITION, "orderTemplateId": tpl_id},
        ))
        return {
            "sessionId": s.id, "participantId": p.id, "condition": SINGLE_CONDITION,
            "orderTemplateId": tpl_id, "caseOrder": list(tpl.order),
            "practiceCaseId": practice.id if practice else "",
        }

    async def complete(self, participant_id: str) -> None:
        p = await self._prepo.get(participant_id)
        if p is not None:
            p.completed_flag = True
            p.completed_at = datetime.now(timezone.utc)
