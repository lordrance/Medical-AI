"""Voice recording endpoints for the L1/L2/L3 open-ended post-survey items.

V4 lets participants record an audio answer for each of the final three
open-ended questions in addition to (or instead of) typing. The audio is
stored on the server's local filesystem under
`backend/data/voice_recordings/<session_id>/<question_id>_<timestamp>.<ext>`
and a metadata row is written to the `voice_recordings` table for admin
auditing and later transcription.

Public endpoint:
  POST /api/voice-recording
        multipart/form-data:
          sessionId    str
          questionId   str
          durationMs   int (optional; -1 / 0 if unknown)
          audio        file (the MediaRecorder Blob)

Admin endpoints (X-Admin-Token required):
  GET  /api/admin/voice-recording/{id}      — stream a single recording
  GET  /api/admin/export/voice-recordings   — ZIP all recordings + index.csv
"""

from __future__ import annotations

import csv
import io
import logging
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.core.security import require_admin
from app.db.models import Session, VoiceRecording

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice-recording"])

# Where recordings are stored on disk. Path is relative to the backend
# working directory (where uvicorn runs from). Added to .gitignore.
_VOICE_DIR = Path(os.environ.get("VOICE_RECORDINGS_DIR", "data/voice_recordings"))

# Max recording size — guard against very long stuck uploads.
_MAX_BYTES = 50 * 1024 * 1024  # 50 MB per recording

# Allowed MIME types from MediaRecorder. Chromium / Firefox default to opus
# in a webm or ogg container; Safari uses MP4 / AAC.
_ALLOWED_MIMES = {
    "audio/webm",
    "audio/webm;codecs=opus",
    "audio/ogg",
    "audio/ogg;codecs=opus",
    "audio/mp4",
    "audio/mpeg",
    "audio/wav",
}


def _ext_for_mime(mime: str) -> str:
    if mime.startswith("audio/webm"):
        return "webm"
    if mime.startswith("audio/ogg"):
        return "ogg"
    if mime.startswith("audio/mp4"):
        return "m4a"
    if mime.startswith("audio/mpeg"):
        return "mp3"
    if mime.startswith("audio/wav"):
        return "wav"
    return "bin"


_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_\-]")


def _safe(s: str) -> str:
    return _SAFE_ID_RE.sub("_", s)[:120]


@router.post("/api/voice-recording")
async def submit_recording(
    sessionId: str = Form(...),
    questionId: str = Form(...),
    durationMs: int = Form(0),
    audio: UploadFile = File(...),
    db: AsyncSession = Depends(db_session),
) -> dict:
    sess = await db.get(Session, sessionId)
    if sess is None:
        raise HTTPException(404, "Unknown session")

    mime = (audio.content_type or "").lower()
    if mime not in _ALLOWED_MIMES:
        raise HTTPException(415, f"unsupported audio mime: {mime!r}")

    blob = await audio.read()
    if not blob:
        raise HTTPException(400, "empty audio payload")
    if len(blob) > _MAX_BYTES:
        raise HTTPException(413, "recording too large")

    safe_session = _safe(sessionId)
    safe_question = _safe(questionId)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    ext = _ext_for_mime(mime)
    rel_dir = _VOICE_DIR / safe_session
    rel_path = rel_dir / f"{safe_question}_{ts}.{ext}"
    try:
        rel_dir.mkdir(parents=True, exist_ok=True)
        rel_path.write_bytes(blob)
    except OSError as e:
        # Storage problem (bind-mount owned by root so the uid-1001 app user
        # can't write, disk full, ...). This is an optional feature, so say so
        # plainly instead of letting it surface as a bare 500 — the recorder
        # button shows the status text verbatim and "HTTP 500" alarms
        # participants into thinking they broke the study.
        logger.error("voice recording write failed at %s: %r", rel_path, e)
        raise HTTPException(
            503, "录音暂时无法保存，请继续用文字作答；这不影响您提交问卷。"
        ) from e

    rec = VoiceRecording(
        session_id=sessionId,
        question_id=questionId,
        file_path=str(rel_path).replace("\\", "/"),
        mime_type=mime,
        duration_ms=durationMs if durationMs and durationMs > 0 else None,
        file_size_bytes=len(blob),
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return {"ok": True, "voiceRecordingId": rec.id, "fileSizeBytes": len(blob)}


@router.get("/api/admin/voice-recording/{recording_id}")
async def get_recording(
    recording_id: str,
    request: Request,
    db: AsyncSession = Depends(db_session),
) -> Response:
    require_admin(request)
    rec = await db.get(VoiceRecording, recording_id)
    if rec is None:
        raise HTTPException(404, "Unknown recording")
    path = Path(rec.file_path)
    if not path.exists():
        raise HTTPException(410, "Recording file is gone from disk")
    return FileResponse(path, media_type=rec.mime_type, filename=path.name)


@router.get("/api/admin/export/voice-recordings")
async def export_recordings(
    request: Request,
    db: AsyncSession = Depends(db_session),
) -> Response:
    """ZIP every recording into voice_recordings.zip with an index.csv that
    maps filenames back to session_id / question_id / created_at."""
    require_admin(request)
    rows = (await db.execute(select(VoiceRecording))).scalars().all()

    # Extract plain data while still on the event loop (no ORM/DB access in the
    # worker thread), then build the ZIP (reads every file + DEFLATE, can be
    # hundreds of MB) off the event loop so it does not freeze this worker and
    # interrupt participants routed to it.
    items = [
        {
            "id": r.id,
            "session_id": r.session_id,
            "question_id": r.question_id,
            "file_path": r.file_path,
            "mime_type": r.mime_type,
            "duration_ms": r.duration_ms if r.duration_ms is not None else "",
            "file_size_bytes": r.file_size_bytes,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in rows
    ]
    payload = await run_in_threadpool(_build_recordings_zip, items)

    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="voice_recordings.zip"',
        },
    )


def _build_recordings_zip(items: list[dict]) -> bytes:
    """Build the recordings ZIP from plain dicts. Runs in a worker thread."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        csv_buf = io.StringIO()
        w = csv.writer(csv_buf)
        w.writerow(
            [
                "voice_recording_id",
                "session_id",
                "question_id",
                "filename_in_zip",
                "mime_type",
                "duration_ms",
                "file_size_bytes",
                "created_at",
            ]
        )
        for it in items:
            p = Path(it["file_path"])
            in_zip = f"{_safe(it['session_id'])}/{p.name}" if p.exists() else "(missing)"
            w.writerow(
                [
                    it["id"],
                    it["session_id"],
                    it["question_id"],
                    in_zip,
                    it["mime_type"],
                    it["duration_ms"],
                    it["file_size_bytes"],
                    it["created_at"],
                ]
            )
            if p.exists():
                zf.writestr(in_zip, p.read_bytes())
        zf.writestr("index.csv", csv_buf.getvalue())
    return buf.getvalue()
