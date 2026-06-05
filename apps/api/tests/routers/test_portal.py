"""Tests for the patient portal router."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

_PRACTICE_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_PATIENT_ID = uuid.uuid4()
_ACCOUNT_ID = uuid.uuid4()
_TOKEN = "b" * 64
_SUB = "cognito-sub-test"
_JWT_CLAIMS = {"sub": _SUB, "email": "jane@example.com", "cognito:groups": []}
_NOW = datetime(2026, 6, 5, 12, 0, 0, tzinfo=UTC)


def _make_patient(**overrides: Any) -> MagicMock:
    row = MagicMock()
    defaults: dict[str, Any] = {
        "id": _PATIENT_ID,
        "practice_id": _PRACTICE_ID,
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane@example.com",
        "deleted_at": None,
    }
    for key, value in {**defaults, **overrides}.items():
        setattr(row, key, value)
    return row


def _make_account(**overrides: Any) -> MagicMock:
    row = MagicMock()
    defaults: dict[str, Any] = {
        "id": _ACCOUNT_ID,
        "practice_id": _PRACTICE_ID,
        "patient_id": _PATIENT_ID,
        "email": "jane@example.com",
        "cognito_sub": None,
        "status": "invited",
        "invite_token": _TOKEN,
        "invite_expires_at": _NOW + timedelta(days=7),
        "invited_at": _NOW,
        "enrolled_at": None,
        "invited_by": _USER_ID,
    }
    for key, value in {**defaults, **overrides}.items():
        setattr(row, key, value)
    return row


@contextmanager
def _mock_auth():
    with patch("app.middleware.auth.jwt.decode", return_value=_JWT_CLAIMS):
        with patch("app.middleware.auth._get_public_key", new=AsyncMock(return_value=object())):
            with patch(
                "app.middleware.auth._resolve_practice_membership",
                new=AsyncMock(return_value=(_USER_ID, "admin")),
            ):
                yield


@pytest.fixture
def client():
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_get_portal_invite_public(client: AsyncClient):
    account = _make_account()
    practice = MagicMock(id=_PRACTICE_ID, name="Smile Dental")
    patient = _make_patient()

    session = MagicMock()
    session.scalar = AsyncMock(side_effect=[account, practice, patient])
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routers.portal.get_session_factory", return_value=session_factory):
        response = await client.get(f"/api/portal/invite/{_TOKEN}")

    assert response.status_code == 200
    body = response.json()
    assert body["practiceName"] == "Smile Dental"
    assert body["patientFirstName"] == "Jane"
    assert body["email"] == "jane@example.com"


@pytest.mark.asyncio
async def test_send_portal_invite_requires_email(client: AsyncClient):
    patient = _make_patient(email=None)

    session = MagicMock()
    session.scalar = AsyncMock(return_value=patient)
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with _mock_auth():
        with patch("app.routers.portal.get_session_factory", return_value=session_factory):
            response = await client.post(
                "/api/v1/portal/invite",
                json={"patientId": str(_PATIENT_ID)},
                headers={
                    "Authorization": "Bearer test-token",
                    "X-Practice-ID": str(_PRACTICE_ID),
                    "Idempotency-Key": str(uuid.uuid4()),
                },
            )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PATIENT_NO_EMAIL"


@pytest.mark.asyncio
async def test_get_portal_status_none(client: AsyncClient):
    patient = _make_patient()

    session = MagicMock()
    session.scalar = AsyncMock(side_effect=[patient, None])
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with _mock_auth():
        with patch("app.routers.portal.get_session_factory", return_value=session_factory):
            response = await client.get(
                f"/api/v1/portal/status?patient_id={_PATIENT_ID}",
                headers={
                    "Authorization": "Bearer test-token",
                    "X-Practice-ID": str(_PRACTICE_ID),
                },
            )

    assert response.status_code == 200
    assert response.json()["status"] == "none"
