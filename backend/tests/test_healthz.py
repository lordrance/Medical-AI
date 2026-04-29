from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_healthz_ok() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["llmProvider"] == "disabled"
    assert body["llmEnabled"] is False


@pytest.mark.asyncio
async def test_openapi_schema_available() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get("/openapi.json")
    assert r.status_code == 200
    data = r.json()
    assert "/healthz" in data["paths"]
