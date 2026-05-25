from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app():
    from app.main import app as _app
    return _app


@pytest.mark.asyncio
async def test_health(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.main._model"):  # skip model load
            resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_transcribe_happy_path(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.main.transcribe", return_value="tooth number fourteen filling"):
            resp = await client.post(
                "/transcribe",
                files={"audio": ("audio.webm", b"fake-bytes", "audio/webm")},
            )
    assert resp.status_code == 200
    assert resp.json()["transcript"] == "tooth number fourteen filling"


@pytest.mark.asyncio
async def test_transcribe_too_large(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.main.transcribe") as mock_t:
            big = b"x" * (25 * 1024 * 1024 + 1)
            resp = await client.post(
                "/transcribe",
                files={"audio": ("audio.webm", big, "audio/webm")},
            )
    assert resp.status_code == 400
    mock_t.assert_not_called()
