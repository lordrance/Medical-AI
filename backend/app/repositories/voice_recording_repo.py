from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import VoiceRecording


class VoiceRecordingRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, recording: VoiceRecording) -> VoiceRecording:
        self._db.add(recording)
        await self._db.flush()
        return recording

    async def get(self, recording_id: str) -> VoiceRecording | None:
        return await self._db.get(VoiceRecording, recording_id)

    async def by_session(self, session_id: str) -> list[VoiceRecording]:
        result = await self._db.execute(
            select(VoiceRecording).where(
                VoiceRecording.session_id == session_id
            )
        )
        return list(result.scalars().all())

    async def all(self) -> list[VoiceRecording]:
        result = await self._db.execute(select(VoiceRecording))
        return list(result.scalars().all())

    async def delete_by_session(self, session_id: str) -> None:
        for vr in await self.by_session(session_id):
            await self._db.delete(vr)
        await self._db.flush()
