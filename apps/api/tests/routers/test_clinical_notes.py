"""
Unit tests for /api/v1/patients/{patient_id}/clinical-notes endpoints.

Auth and DB are fully mocked — no real Postgres, Cognito, or Redis needed.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ── Constants ─────────────────────────────────────────────────────────────────

_PRACTICE_ID = uuid.uuid4()
_PRACTICE_B_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_PATIENT_ID = uuid.uuid4()
_NOTE_ID = uuid.uuid4()
_PROVIDER_ID = uuid.uuid4()
_APPOINTMENT_ID = uuid.uuid4()
_SUB = "cognito-sub-test"
_JWT_CLAIMS = {"sub": _SUB, "email": "staff@clinic.com", "cognito:groups": []}

_TODAY = date(2026, 5, 3)
_NOW = datetime(2026, 5, 3, 12, 0, 0, tzinfo=UTC)

_NOTE_ROW_DEFAULTS: dict[str, Any] = {
    "id": _NOTE_ID,
    "practice_id": _PRACTICE_ID,
    "patient_id": _PATIENT_ID,
    "appointment_id": None,
    "provider_id": _PROVIDER_ID,
    "visit_date": _TODAY,
    "chief_complaint": "Tooth pain",
    "anesthesia": None,
    "patient_tolerance": None,
    "complications": None,
    "treatment_rendered": "Exam and X-rays completed",
    "next_visit_plan": None,
    "notes": None,
    "template_type": "exam",
    "is_signed": False,
    "signed_at": None,
    "signed_by_provider_id": None,
    "created_at": _NOW,
    "updated_at": _NOW,
    "last_accessed_by": None,
    "last_accessed_at": None,
    "deleted_at": None,
}

_PATIENT_ROW_DEFAULTS: dict[str, Any] = {
    "id": _PATIENT_ID,
    "practice_id": _PRACTICE_ID,
    "deleted_at": None,
}

_APPOINTMENT_ROW_DEFAULTS: dict[str, Any] = {
    "id": _APPOINTMENT_ID,
    "practice_id": _PRACTICE_ID,
    "patient_id": _PATIENT_ID,
}


def _make_note_row(**overrides: Any) -> MagicMock:
    row = MagicMock()
    for k, v in {**_NOTE_ROW_DEFAULTS, **overrides}.items():
        setattr(row, k, v)
    return row


def _make_patient_row(**overrides: Any) -> MagicMock:
    row = MagicMock()
    for k, v in {**_PATIENT_ROW_DEFAULTS, **overrides}.items():
        setattr(row, k, v)
    return row


def _make_appointment_row(**overrides: Any) -> MagicMock:
    row = MagicMock()
    for k, v in {**_APPOINTMENT_ROW_DEFAULTS, **overrides}.items():
        setattr(row, k, v)
    return row


def _get_app():
    import os

    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    os.environ.setdefault("APP_ENCRYPTION_KEY", "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXQ=")
    from app.main import create_app

    return create_app()


@contextmanager
def _auth_patches(practice_id: uuid.UUID | None = _PRACTICE_ID, role: str = "front_desk"):
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


def _make_session(
    scalar_returns: list | None = None,
    scalars_returns: list | None = None,
) -> AsyncMock:
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()

    if scalar_returns is not None:
        session.scalar = AsyncMock(side_effect=scalar_returns)

    if scalars_returns is not None:
        mock_scalars_result = MagicMock()
        mock_scalars_result.all.return_value = scalars_returns
        session.scalars = AsyncMock(return_value=mock_scalars_result)

    return session


# ── Auth tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_unauthenticated_returns_401():
    app = _get_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get(f"/api/v1/patients/{_PATIENT_ID}/clinical-notes")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_unauthenticated_returns_401():
    app = _get_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.post(
            f"/api/v1/patients/{_PATIENT_ID}/clinical-notes",
            json={
                "providerId": str(_PROVIDER_ID),
                "visitDate": "2026-05-03",
                "treatmentRendered": "Exam completed",
            },
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_read_only_role_returns_403():
    app = _get_app()
    session = _make_session()
    with (
        _auth_patches(role="read_only") as auth_headers,
        patch("app.routers.clinical_notes.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                f"/api/v1/patients/{_PATIENT_ID}/clinical-notes",
                json={
                    "providerId": str(_PROVIDER_ID),
                    "visitDate": "2026-05-03",
                    "treatmentRendered": "Exam completed",
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_practice_b_sees_no_practice_a_notes():
    """Practice B user querying a Practice A patient sees an empty list.

    Isolation is enforced by the practice_id filter in the query — no Practice B
    notes exist for this patient, so the result is always empty.
    """
    app = _get_app()
    session = _make_session(scalars_returns=[])
    with (
        _auth_patches(practice_id=_PRACTICE_B_ID) as auth_headers,
        patch("app.routers.clinical_notes.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/patients/{_PATIENT_ID}/clinical-notes",
                headers=auth_headers,
            )
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["hasMore"] is False


@pytest.mark.asyncio
async def test_no_practice_membership_returns_403():
    """User without membership in any practice gets 403."""
    app = _get_app()
    session = _make_session()
    with (
        _auth_patches(practice_id=None) as auth_headers,
        patch("app.routers.clinical_notes.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/patients/{_PATIENT_ID}/clinical-notes",
                headers=auth_headers,
            )
    assert response.status_code == 403


# ── GET list ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_returns_notes_with_no_cursor():
    app = _get_app()
    note = _make_note_row()
    session = _make_session(scalars_returns=[note])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.clinical_notes.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/patients/{_PATIENT_ID}/clinical-notes",
                headers=auth_headers,
            )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["hasMore"] is False
    assert data["nextCursor"] is None
    assert data["items"][0]["treatmentRendered"] == "Exam and X-rays completed"


@pytest.mark.asyncio
async def test_list_returns_cursor_when_more_pages_exist():
    """When limit+1 rows are returned, hasMore=True and nextCursor is set."""
    app = _get_app()
    # Return limit+1 rows (limit=2, return 3)
    notes = [_make_note_row(id=uuid.uuid4(), visit_date=_TODAY) for _ in range(3)]
    session = _make_session(scalars_returns=notes)
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.clinical_notes.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/patients/{_PATIENT_ID}/clinical-notes?limit=2",
                headers=auth_headers,
            )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["hasMore"] is True
    assert data["nextCursor"] is not None


@pytest.mark.asyncio
async def test_list_empty_returns_no_cursor():
    app = _get_app()
    session = _make_session(scalars_returns=[])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.clinical_notes.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/patients/{_PATIENT_ID}/clinical-notes",
                headers=auth_headers,
            )
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["hasMore"] is False
    assert data["nextCursor"] is None


# ── POST create ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_note_returns_201():
    app = _get_app()
    patient = _make_patient_row()
    session = _make_session(scalar_returns=[patient])
    session.refresh = AsyncMock(side_effect=lambda row: None)

    def _set_row_attrs(row: Any) -> None:
        for k, v in _NOTE_ROW_DEFAULTS.items():
            setattr(row, k, v)

    session.refresh = AsyncMock(side_effect=_set_row_attrs)
    # The added row will be a real ClinicalNote-like mock
    added_row = _make_note_row()
    session.add = MagicMock()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.clinical_notes.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        # Patch ClinicalNoteModel constructor to return our mock
        with patch(
            "app.routers.clinical_notes.ClinicalNoteModel",
            return_value=added_row,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                response = await c.post(
                    f"/api/v1/patients/{_PATIENT_ID}/clinical-notes",
                    json={
                        "providerId": str(_PROVIDER_ID),
                        "visitDate": "2026-05-03",
                        "treatmentRendered": "Exam completed",
                        "templateType": "exam",
                    },
                    headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
                )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_create_note_patient_not_found_returns_404():
    app = _get_app()
    session = _make_session(scalar_returns=[None])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.clinical_notes.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                f"/api/v1/patients/{_PATIENT_ID}/clinical-notes",
                json={
                    "providerId": str(_PROVIDER_ID),
                    "visitDate": "2026-05-03",
                    "treatmentRendered": "Exam completed",
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PATIENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_create_note_wrong_patient_appointment_returns_400():
    """appointment_id belonging to a different patient is rejected with 400."""
    app = _get_app()
    patient = _make_patient_row()
    # Appointment returns None because it doesn't match the patient
    session = _make_session(scalar_returns=[patient, None])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.clinical_notes.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                f"/api/v1/patients/{_PATIENT_ID}/clinical-notes",
                json={
                    "providerId": str(_PROVIDER_ID),
                    "visitDate": "2026-05-03",
                    "treatmentRendered": "Exam completed",
                    "appointmentId": str(uuid.uuid4()),
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_APPOINTMENT"


# ── PATCH update ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_unsigned_note_succeeds():
    app = _get_app()
    note = _make_note_row(is_signed=False)
    session = _make_session(scalar_returns=[note])

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.clinical_notes.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.patch(
                f"/api/v1/patients/{_PATIENT_ID}/clinical-notes/{_NOTE_ID}",
                json={"treatmentRendered": "Updated treatment note"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_update_signed_note_returns_409():
    """Editing a signed note must return 409 with NOTE_ALREADY_SIGNED."""
    app = _get_app()
    note = _make_note_row(is_signed=True, signed_at=_NOW)
    session = _make_session(scalar_returns=[note])

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.clinical_notes.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.patch(
                f"/api/v1/patients/{_PATIENT_ID}/clinical-notes/{_NOTE_ID}",
                json={"treatmentRendered": "Attempted edit after signing"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOTE_ALREADY_SIGNED"


# ── POST sign ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sign_unsigned_note_succeeds():
    app = _get_app()
    note = _make_note_row(is_signed=False)
    session = _make_session(scalar_returns=[note])

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.clinical_notes.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                f"/api/v1/patients/{_PATIENT_ID}/clinical-notes/{_NOTE_ID}/sign",
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_sign_already_signed_note_returns_409():
    """Second sign attempt on an already-signed note must return 409."""
    app = _get_app()
    note = _make_note_row(is_signed=True, signed_at=_NOW)
    session = _make_session(scalar_returns=[note])

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.clinical_notes.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                f"/api/v1/patients/{_PATIENT_ID}/clinical-notes/{_NOTE_ID}/sign",
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOTE_ALREADY_SIGNED"


@pytest.mark.asyncio
async def test_sign_note_read_only_role_returns_403():
    app = _get_app()
    session = _make_session()
    with (
        _auth_patches(role="read_only") as auth_headers,
        patch("app.routers.clinical_notes.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                f"/api/v1/patients/{_PATIENT_ID}/clinical-notes/{_NOTE_ID}/sign",
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 403


# ── GET detail ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_detail_not_found_returns_404():
    app = _get_app()
    session = _make_session(scalar_returns=[None])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.clinical_notes.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/patients/{_PATIENT_ID}/clinical-notes/{_NOTE_ID}",
                headers=auth_headers,
            )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOTE_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_detail_returns_full_note():
    app = _get_app()
    note = _make_note_row()
    session = _make_session(scalar_returns=[note])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.clinical_notes.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/patients/{_PATIENT_ID}/clinical-notes/{_NOTE_ID}",
                headers=auth_headers,
            )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(_NOTE_ID)
    assert data["treatmentRendered"] == "Exam and X-rays completed"
    assert data["isSigned"] is False


# ── Cursor encoding ───────────────────────────────────────────────────────────


def test_cursor_encode_decode_roundtrip():
    from app.routers.clinical_notes import _decode_cursor, _encode_cursor

    d = date(2026, 5, 3)
    note_id = uuid.uuid4()
    cursor = _encode_cursor(d, note_id)
    result = _decode_cursor(cursor)
    assert result is not None
    assert result[0] == d
    assert result[1] == note_id


def test_cursor_decode_invalid_returns_none():
    from app.routers.clinical_notes import _decode_cursor

    assert _decode_cursor("not-valid-base64!!!") is None
    assert _decode_cursor("aW52YWxpZA==") is None  # valid base64, invalid JSON structure
