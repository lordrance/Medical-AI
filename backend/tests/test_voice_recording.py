"""Tests for V4 voice recording endpoints (L1/L2/L3 audio capture)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.models import VoiceRecording
from app.db.session import get_session_factory


async def _start_session(client: AsyncClient) -> dict:
    r = await client.post("/api/session")
    assert r.status_code == 200
    return r.json()


@pytest.fixture(autouse=True)
async def _isolated_voice_dir(tmp_path, monkeypatch):
    """Each test writes audio to a throwaway directory so we don't pollute
    backend/data/voice_recordings/. The endpoint reads VOICE_RECORDINGS_DIR
    at import time, so monkeypatch the module-level _VOICE_DIR directly."""
    from app.api import voice_recording as vr_mod

    monkeypatch.setattr(vr_mod, "_VOICE_DIR", tmp_path / "voice")
    yield


@pytest.fixture(autouse=True)
async def _seed():
    from app.scripts.seed import upsert_cases, upsert_order_templates

    await upsert_cases()
    await upsert_order_templates()


@pytest.mark.asyncio
async def test_submit_recording_stores_file_and_row(
    client: AsyncClient, tmp_path
) -> None:
    s = await _start_session(client)
    fake_audio = b"\x1a\x45\xdf\xa3" + b"\x00" * 200  # webm magic + filler
    r = await client.post(
        "/api/voice-recording",
        data={
            "sessionId": s["sessionId"],
            "questionId": "post_qual_l1_ehr_pain_ai_substitution",
            "durationMs": "12500",
        },
        files={"audio": ("rec.webm", fake_audio, "audio/webm")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["voiceRecordingId"]
    assert body["fileSizeBytes"] == len(fake_audio)

    factory = get_session_factory()
    async with factory() as session:
        rows = (await session.execute(select(VoiceRecording))).scalars().all()
    assert len(rows) == 1
    rec = rows[0]
    assert rec.session_id == s["sessionId"]
    assert rec.question_id == "post_qual_l1_ehr_pain_ai_substitution"
    assert rec.mime_type == "audio/webm"
    assert rec.duration_ms == 12500
    assert rec.file_size_bytes == len(fake_audio)
    assert Path(rec.file_path).exists()
    assert Path(rec.file_path).read_bytes() == fake_audio


@pytest.mark.asyncio
async def test_submit_recording_rejects_unknown_session(client: AsyncClient) -> None:
    r = await client.post(
        "/api/voice-recording",
        data={"sessionId": "nonexistent", "questionId": "q"},
        files={"audio": ("rec.webm", b"x" * 64, "audio/webm")},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_submit_recording_rejects_unsupported_mime(client: AsyncClient) -> None:
    s = await _start_session(client)
    r = await client.post(
        "/api/voice-recording",
        data={"sessionId": s["sessionId"], "questionId": "q"},
        files={"audio": ("evil.exe", b"x" * 64, "application/x-msdownload")},
    )
    assert r.status_code == 415


@pytest.mark.asyncio
async def test_admin_can_download_individual_recording(
    client: AsyncClient, admin_token: str
) -> None:
    s = await _start_session(client)
    payload_bytes = b"opus-bytes" * 32
    r = await client.post(
        "/api/voice-recording",
        data={"sessionId": s["sessionId"], "questionId": "post_qual_l2_human_ai_boundary"},
        files={"audio": ("r.webm", payload_bytes, "audio/webm")},
    )
    rid = r.json()["voiceRecordingId"]

    # No token → 401
    no_auth = await client.get(f"/api/admin/voice-recording/{rid}")
    assert no_auth.status_code == 401

    # With token → 200, bytes match
    ok = await client.get(
        f"/api/admin/voice-recording/{rid}",
        headers={"X-Admin-Token": admin_token},
    )
    assert ok.status_code == 200
    assert ok.content == payload_bytes


@pytest.mark.asyncio
async def test_admin_can_export_all_recordings_as_zip(
    client: AsyncClient, admin_token: str
) -> None:
    s = await _start_session(client)
    # Upload two recordings against different question IDs
    for qid, blob in [
        ("post_qual_l1_ehr_pain_ai_substitution", b"AAA" * 50),
        ("post_qual_l3_system_transformation", b"BBB" * 50),
    ]:
        await client.post(
            "/api/voice-recording",
            data={"sessionId": s["sessionId"], "questionId": qid},
            files={"audio": ("r.webm", blob, "audio/webm")},
        )

    r = await client.get(
        "/api/admin/export/voice-recordings",
        headers={"X-Admin-Token": admin_token},
    )
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert "index.csv" in names
    # Two audio files + index.csv
    audio_names = [n for n in names if n != "index.csv"]
    assert len(audio_names) == 2
    index = zf.read("index.csv").decode("utf-8")
    assert "post_qual_l1_ehr_pain_ai_substitution" in index
    assert "post_qual_l3_system_transformation" in index
    assert s["sessionId"] in index
