from __future__ import annotations

import io
import zipfile

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_full_database_export_sqlite(client: AsyncClient, admin_token: str) -> None:
    r = await client.get(
        "/api/admin/export/full-database",
        headers={"X-Admin-Token": admin_token},
    )
    assert r.status_code == 200
    assert b"CREATE TABLE" in r.content or b"BEGIN TRANSACTION" in r.content


@pytest.mark.asyncio
async def test_export_bundle_zip_default(client: AsyncClient, admin_token: str) -> None:
    r = await client.get(
        "/api/admin/export/bundle",
        headers={"X-Admin-Token": admin_token},
    )
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/zip")
    buf = io.BytesIO(r.content)
    with zipfile.ZipFile(buf) as zf:
        names = set(zf.namelist())
    assert "actions.csv" in names
    assert "ui_events.csv" in names
    assert "cases.csv" in names
    assert "summary.csv" in names


@pytest.mark.asyncio
async def test_export_bundle_partial_tables(client: AsyncClient, admin_token: str) -> None:
    r = await client.get(
        "/api/admin/export/bundle",
        headers={"X-Admin-Token": admin_token},
        params={"tables": "participants,actions"},
    )
    assert r.status_code == 200
    buf = io.BytesIO(r.content)
    with zipfile.ZipFile(buf) as zf:
        names = set(zf.namelist())
    assert names == {"participants.csv", "actions.csv"}
