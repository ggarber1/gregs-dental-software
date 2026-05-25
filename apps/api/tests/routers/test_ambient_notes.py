"""
Unit tests for POST /api/v1/patients/{patient_id}/ambient-note-draft.

All external I/O (Whisper, Bedrock, Auth, Redis) is mocked.
"""
from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

_PRACTICE_ID = uuid.uuid4()
_PATIENT_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_JWT_CLAIMS = {"sub": "test-sub", "email": "dr@clinic.com", "cognito:groups": []}

_DRAFT = (
    "CC: Restoration\n"
    "Anesthesia: Lidocaine 2% 1:100,000 epinephrine, 1.7 mL\n"
    "Treatment: Composite restoration (D2391) tooth #14.\n"
    "Next visit: Routine recall."
)


def _get_app():
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    os.environ.setdefault("APP_ENCRYPTION_KEY", "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXQ=")
    from app.main import create_app
    return create_app()


@contextmanager
def _auth_patches(practice_id: uuid.UUID | None = _PRACTICE_ID, role: str = "provider"):
    membership_result = (_USER_ID, role) if practice_id is not None else None
    headers: dict[str, str] = {"Authorization": "Bearer fake.jwt.token"}
    if practice_id is not None:
        headers["X-Practice-ID"] = str(practice_id)

    with (
        patch("jose.jwt.get_unverified_header", return_value={"kid": "fake-kid"}),
        patch("app.middleware.auth._get_public_key", new=AsyncMock(return_value=object())),
        patch("jose.jwt.decode", return_value=_JWT_CLAIMS),
        patch(
            "app.middleware.auth._resolve_practice_membership",
            new=AsyncMock(return_value=membership_result),
        ),
        patch(
            "app.middleware.idempotency.get_redis",
            return_value=AsyncMock(get=AsyncMock(return_value=None), setex=AsyncMock()),
        ),
    ):
        yield headers


@pytest.fixture
def app():
    return _get_app()


@pytest.mark.asyncio
async def test_happy_path(app):
    with (
        _auth_patches() as auth_headers,
        patch(
            "app.routers.ambient_notes.whisper_client.transcribe",
            new=AsyncMock(return_value="patient got a filling on tooth fourteen"),
        ),
        patch(
            "app.routers.ambient_notes.bedrock_extraction.draft_note",
            new=AsyncMock(return_value={"draft": _DRAFT, "detected_template": "filling"}),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/patients/{_PATIENT_ID}/ambient-note-draft",
                files={"audio": ("audio.webm", b"fake-audio", "audio/webm")},
                headers=auth_headers,
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["draft"] == _DRAFT
    assert body["detectedTemplate"] == "filling"


@pytest.mark.asyncio
async def test_audio_too_large(app):
    with _auth_patches() as auth_headers:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            big = b"x" * (25 * 1024 * 1024 + 1)
            resp = await client.post(
                f"/api/v1/patients/{_PATIENT_ID}/ambient-note-draft",
                files={"audio": ("audio.webm", big, "audio/webm")},
                headers=auth_headers,
            )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_whisper_unavailable_returns_502(app):
    from app.services.whisper_client import WhisperUnavailableError

    with (
        _auth_patches() as auth_headers,
        patch(
            "app.routers.ambient_notes.whisper_client.transcribe",
            new=AsyncMock(side_effect=WhisperUnavailableError("not configured")),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/patients/{_PATIENT_ID}/ambient-note-draft",
                files={"audio": ("audio.webm", b"fake", "audio/webm")},
                headers=auth_headers,
            )
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_whisper_timeout_returns_504(app):
    from app.services.whisper_client import WhisperTimeoutError

    with (
        _auth_patches() as auth_headers,
        patch(
            "app.routers.ambient_notes.whisper_client.transcribe",
            new=AsyncMock(side_effect=WhisperTimeoutError("timed out")),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/patients/{_PATIENT_ID}/ambient-note-draft",
                files={"audio": ("audio.webm", b"fake", "audio/webm")},
                headers=auth_headers,
            )
    assert resp.status_code == 504


@pytest.mark.asyncio
async def test_bedrock_failure_returns_502(app):
    from app.services.bedrock_extraction import BedrockExtractionError

    with (
        _auth_patches() as auth_headers,
        patch(
            "app.routers.ambient_notes.whisper_client.transcribe",
            new=AsyncMock(return_value="some transcript"),
        ),
        patch(
            "app.routers.ambient_notes.bedrock_extraction.draft_note",
            new=AsyncMock(side_effect=BedrockExtractionError("bedrock down")),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/patients/{_PATIENT_ID}/ambient-note-draft",
                files={"audio": ("audio.webm", b"fake", "audio/webm")},
                headers=auth_headers,
            )
    assert resp.status_code == 502
