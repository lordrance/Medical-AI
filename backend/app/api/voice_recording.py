"""
================================================================================
文件作用：语音录音的上传和下载（★ V4 前端已停用，接口保留）
================================================================================

★ 当前状态：这个功能在前端已经关掉了（见 frontend/src/app/post-survey/
  page.tsx 里被注释掉的那段）。医生看不到录音按钮，所以下面这个上传接口
  实际上没人会调，生产库里 voice_recordings 表是 0 行。

  关掉的原因：它是整个流程里最不可靠的一环——要麦克风权限、要浏览器支持
  MediaRecorder、还要在手机网络上传好几 MB，而且失败提示出现在最后一页，
  很容易吓跑医生。而分析用的是文字答案，录音只是锦上添花。

  代码保留是为了将来想恢复时不用重写；也因为删掉它要动路由注册、
  导出功能和 5 个测试，为零收益引入风险。

原本的设计：后测最后三道开放题，医生可以录一段语音代替打字，
研究团队事后人工转写。

  音频文件存服务器磁盘：backend/data/voice_recordings/<会话id>/<题号>_<时间>.<扩展名>
  数据库只存路径和元信息（大文件塞进数据库会让备份变得极慢）

--------------------------------------------------------------------------------
★ 一个踩过的坑
--------------------------------------------------------------------------------
docker-compose 把宿主机的 data/voice_recordings 挂进容器。如果这个目录
不存在，Docker 会用 root 身份建出来，而容器里的应用跑在 uid 1001，
写不进去 → 上传报 500。上海服务器就这么坏过（tarball 迁移时目录被 root 重建）。
现在 deploy/setup.sh 会提前建好目录并设对属主。

--------------------------------------------------------------------------------
本文件的代码块（从上到下）：
--------------------------------------------------------------------------------
  第 1 块  _VOICE_DIR / _MAX_BYTES / _ALLOWED_MIMES  存储位置和限制
  第 2 块  几个小工具                 文件名清洗、扩展名推断
  第 3 块  submit_recording()         上传录音（医生端，已停用）
  第 4 块  get_recording()            下载单个录音（管理员）
  第 5 块  export_all_recordings()    打包下载全部录音（管理员）
================================================================================
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
# ── 第 1 块：存储位置和限制 ──────────────────────────────────────────────
# 音频存哪。生产环境由 docker-compose 注入成 /app/data/voice_recordings，
# 那个路径又挂载到宿主机上，所以容器重建后文件还在。
_VOICE_DIR = Path(os.environ.get("VOICE_RECORDINGS_DIR", "data/voice_recordings"))

# Max recording size — guard against very long stuck uploads.
# 单个录音最大 50 MB。50 MB 的 webm/opus 差不多是两小时以上的音频，
# 正常录音远远到不了，这个限制是防止有人上传超大文件把磁盘撑爆。
# ★ Caddy 那边也有一道同样的限制（见 deploy/Caddyfile），双保险。
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


# ── 第 2 块：两个小工具 ──────────────────────────────────────────────────
def _ext_for_mime(mime: str) -> str:
    """根据音频类型推断文件扩展名。

    浏览器录出来的格式各不相同：Chrome / Firefox 默认是 webm 装 opus，
    Safari 用 mp4 装 aac。存盘时给对扩展名，你下载下来才能双击直接播放。
    认不出来的一律叫 .bin，总比叫错强。
    """
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


# 匹配"除了字母、数字、下划线、横杠之外的所有字符"。
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_\-]")


def _safe(s: str) -> str:
    """把一段文字洗成能安全当文件名的样子。

    ★ 这是防「路径穿越攻击」的关键一步。
    会话编号和题号会被拼进文件路径。如果不清洗，别人传一个
    形如 "../../etc/passwd" 的题号进来，文件就会被写到你不希望的地方。
    把所有特殊字符（包括斜杠和点）统统换成下划线，就不可能跳出目录了。

    再截断到 120 个字符：文件系统对路径长度有上限，超了会写入失败。
    """
    return _SAFE_ID_RE.sub("_", s)[:120]


# ── 第 3 块：上传录音（医生端，已停用）──────────────────────────────────
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


# ── 第 4 块：下载单个录音（管理员）──────────────────────────────────────
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


# ── 第 5 块：打包下载全部录音（管理员）──────────────────────────────────
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
