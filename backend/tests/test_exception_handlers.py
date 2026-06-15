"""Unit tests for the global exception handler module.

Verifies that all three registered handlers (HTTPException, RequestValidationError,
generic Exception) produce the standard structured response with request_id,
timestamp, and type fields.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from starlette.requests import Request

from app.core.exception_handlers import (
    _get_request_id,
    _sanitize_errors,
    _timestamp,
    register_exception_handlers,
)


# ---------------------------------------------------------------------------
# unit tests for internal helpers
# ---------------------------------------------------------------------------


def test_timestamp_format() -> None:
    ts = _timestamp()
    assert ts.endswith("Z"), f"expected UTC Z suffix, got {ts!r}"
    # Parseable as ISO 8601
    from datetime import datetime

    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert parsed is not None


def test_get_request_id_fallback() -> None:
    """When structlog context is empty _get_request_id falls back to header."""
    from starlette.testclient import TestClient as StarletteClient

    app = FastAPI()

    @app.get("/check")
    async def check(request: Request):
        return {
            "rid": _get_request_id(request),
        }

    client = StarletteClient(app, raise_server_exceptions=False)
    resp = client.get("/check", headers={"X-Request-ID": "my-trace-id"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["rid"] == "my-trace-id"


def test_get_request_id_unknown() -> None:
    """Without header or context, returns 'unknown'."""
    from starlette.testclient import TestClient as StarletteClient

    app = FastAPI()

    @app.get("/check")
    async def check(request: Request):
        return {
            "rid": _get_request_id(request),
        }

    client = StarletteClient(app, raise_server_exceptions=False)
    resp = client.get("/check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["rid"] == "unknown"


def test_sanitize_errors_converts_non_serializable() -> None:
    """Pydantic errors with non-serializable ctx values are stringified."""
    raw = [
        {
            "type": "value_error",
            "loc": ("body",),
            "msg": "Value error, escalateReason is required when escalating",
            "input": {},
            "ctx": {"error": ValueError("escalateReason is required")},
        }
    ]
    sanitized = _sanitize_errors(raw)
    # Should not raise when serialized
    json.dumps(sanitized)
    assert isinstance(sanitized[0]["ctx"]["error"], str)
    assert "escalateReason" in sanitized[0]["ctx"]["error"]


def test_sanitize_errors_preserves_serializable() -> None:
    """Already-JSON-safe errors pass through unchanged.

    Note: tuples are not JSON-serializable so _sanitize_errors stringifies
    them. Only the string representation is preserved.
    """
    raw = [
        {
            "type": "missing",
            "loc": ("body", "name"),
            "msg": "Field required",
            "input": {},
        }
    ]
    sanitized = _sanitize_errors(raw)
    json.dumps(sanitized)
    assert sanitized[0]["type"] == "missing"
    # Tuple gets stringified because it's not in the safe-types whitelist
    assert isinstance(sanitized[0]["loc"], str)


# ---------------------------------------------------------------------------
# integration tests via TestClient on a minimal app
# ---------------------------------------------------------------------------


def _make_test_app() -> FastAPI:
    app = FastAPI()

    @app.get("/http-error")
    async def raise_http():
        raise HTTPException(403, "Forbidden")

    @app.get("/server-error")
    async def raise_server():
        raise ValueError("database connection failed")

    class InputModel(BaseModel):
        name: str = Field(min_length=1)

    @app.post("/validate")
    async def validate(body: InputModel):
        return {"ok": True}

    register_exception_handlers(app)
    return app


class TestHttpExceptionHandler:
    def test_403_response_shape(self) -> None:
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/http-error")
        assert resp.status_code == 403
        data = resp.json()
        assert data["detail"] == "Forbidden"
        assert data["type"] == "http_error"
        assert "request_id" in data
        assert "timestamp" in data

    def test_404_response_shape(self) -> None:
        """Our HTTPException handler fires for explicit 404 raises."""
        app = _make_test_app()

        @app.get("/explicit-404")
        async def explicit_404():
            raise HTTPException(404, "Custom not found")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/explicit-404")
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"] == "Custom not found"
        assert data["type"] == "http_error"
        assert "request_id" in data
        assert "timestamp" in data


class TestValidationErrorHandler:
    def test_422_response_shape(self) -> None:
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/validate", json={"name": ""})
        assert resp.status_code == 422
        data = resp.json()
        assert data["type"] == "validation_error"
        assert isinstance(data["detail"], list)
        assert "request_id" in data
        assert "timestamp" in data

    def test_422_on_invalid_json_body(self) -> None:
        """Malformed JSON body triggers RequestValidationError too."""
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/validate",
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["type"] == "validation_error"


class TestGeneralExceptionHandler:
    def test_500_response_shape(self) -> None:
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/server-error")
        assert resp.status_code == 500
        data = resp.json()
        assert data["detail"] == "Internal server error"
        assert data["type"] == "internal_error"
        assert "request_id" in data
        assert "timestamp" in data

    def test_500_never_leaks_internals(self) -> None:
        """The 500 handler must not expose the exception message."""
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/server-error")
        data = resp.json()
        assert "database connection failed" not in data["detail"]
        assert "ValueError" not in data["detail"]
