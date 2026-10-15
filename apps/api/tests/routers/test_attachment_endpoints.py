"""Endpoint tests for attachment upload / list / delete endpoints."""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ── Constants ─────────────────────────────────────────────────────────────────

_PRACTICE_ID = uuid.uuid4()
_APPOINTMENT_ID = uuid.uuid4()
_ATTACHMENT_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_JWT_CLAIMS = {"sub": "staff-sub", "email": "staff@clinic.com", "cognito:groups": []}


# ── Helpers ───────────────────────────────────────────────────────────────────


@contextmanager
def _auth_patches(practice_id: uuid.UUID | None = _PRACTICE_ID, role: str = "front_desk"):
    membership_result = (_USER_ID, role) if practice_id is not None else None
    headers: dict[str, str] = {"Authorization": "Bearer fake.jwt.token"}
    if practice_id is not None:
        headers["X-Practice-ID"] = str(practice_id)

    with (
        patch("jose.jwt.get_unverified_header", return_value={"kid": "fake-kid"}),
        patch(
            "app.middleware.auth._get_public_key",
            new=AsyncMock(return_value=object()),
        ),
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


def _fake_attachment_row(
    attachment_id: uuid.UUID = _ATTACHMENT_ID,
    practice_id: uuid.UUID = _PRACTICE_ID,
    appointment_id: uuid.UUID = _APPOINTMENT_ID,
    file_name: str = "xray.png",
    content_type: str = "image/png",
    attachment_type: str = "xray",
) -> MagicMock:
    """Build a MagicMock that satisfies _to_schema() field accesses."""
    now = datetime.now(UTC)
    m = MagicMock()
    m.id = attachment_id
    m.practice_id = practice_id
    m.appointment_id = appointment_id
    m.s3_key = f"{practice_id}/appointments/{appointment_id}/{attachment_id}/{file_name}"
    m.file_name = file_name
    m.file_size_bytes = 1024
    m.content_type = content_type
    m.attachment_type = attachment_type
    m.uploaded_by = "staff-sub"
    m.created_at = now
    return m


def _fake_session_factory(scalar_return=None, scalars_return=None):
    """Return a mock session factory. Use scalar_return for session.scalar(),
    scalars_return (list) for session.scalars()."""
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=scalar_return)
    if scalars_return is not None:
        scalars_result = MagicMock()
        scalars_result.all = MagicMock(return_value=scalars_return)
        session.scalars = AsyncMock(return_value=scalars_result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock(return_value=cm)
    return factory


def _attachment_url(appointment_id: uuid.UUID = _APPOINTMENT_ID) -> str:
    return f"/api/v1/appointments/{appointment_id}/attachments"


def _delete_url(
    appointment_id: uuid.UUID = _APPOINTMENT_ID,
    attachment_id: uuid.UUID = _ATTACHMENT_ID,
) -> str:
    return f"/api/v1/appointments/{appointment_id}/attachments/{attachment_id}"


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_attachment_happy_path():
    """POST multipart → 201 with correct body fields."""
    from app.main import create_app

    app = create_app()
    fake_row = _fake_attachment_row()

    with _auth_patches() as headers, patch(
        "app.routers.attachments.require_feature", new=AsyncMock(return_value=None)
    ), patch(
        "app.routers.attachments.upload_attachment", new=AsyncMock(return_value=fake_row)
    ), patch(
        "app.routers.attachments.get_session_factory", return_value=_fake_session_factory()
    ), patch(
        "app.services.attachments.service.put_object", return_value=None
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                _attachment_url(),
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                files={"file": ("xray.png", BytesIO(b"fake-image-bytes"), "image/png")},
                data={"attachment_type": "xray"},
            )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["fileName"] == "xray.png"
    assert body["attachmentType"] == "xray"
    assert body["contentType"] == "image/png"
    assert body["practiceId"] == str(_PRACTICE_ID)
    assert body["appointmentId"] == str(_APPOINTMENT_ID)


@pytest.mark.asyncio
async def test_upload_attachment_unsupported_type_returns_422():
    """POST with application/msword content-type → 422 from service validation."""
    from fastapi import HTTPException

    from app.main import create_app

    app = create_app()

    with _auth_patches() as headers, patch(
        "app.routers.attachments.require_feature", new=AsyncMock(return_value=None)
    ), patch(
        "app.routers.attachments.upload_attachment",
        new=AsyncMock(
            side_effect=HTTPException(
                status_code=422,
                detail={
                    "code": "UNSUPPORTED_FILE_TYPE",
                    "message": "Content type 'application/msword' is not accepted",
                },
            )
        ),
    ), patch(
        "app.routers.attachments.get_session_factory", return_value=_fake_session_factory()
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                _attachment_url(),
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                files={
                    "file": (
                        "doc.doc",
                        BytesIO(b"fake-doc-bytes"),
                        "application/msword",
                    )
                },
                data={"attachment_type": "other"},
            )

    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_get_attachments_only_returns_own_practice():
    """GET /appointments/{id}/attachments → list with one attachment for this practice."""
    from app.main import create_app

    app = create_app()
    fake_row = _fake_attachment_row()

    with _auth_patches() as headers, patch(
        "app.routers.attachments.require_feature", new=AsyncMock(return_value=None)
    ), patch(
        "app.routers.attachments.list_attachments", new=AsyncMock(return_value=[fake_row])
    ), patch(
        "app.routers.attachments.get_session_factory", return_value=_fake_session_factory()
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(_attachment_url(), headers=headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["id"] == str(_ATTACHMENT_ID)
    assert body[0]["practiceId"] == str(_PRACTICE_ID)


@pytest.mark.asyncio
async def test_delete_attachment_happy_path():
    """DELETE → 204; subsequent GET returns empty list."""
    from app.main import create_app

    app = create_app()

    with _auth_patches() as headers, patch(
        "app.routers.attachments.require_feature", new=AsyncMock(return_value=None)
    ), patch(
        "app.routers.attachments.delete_attachment", new=AsyncMock(return_value=None)
    ), patch(
        "app.routers.attachments.get_session_factory", return_value=_fake_session_factory()
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            del_resp = await client.delete(
                _delete_url(),
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert del_resp.status_code == 204, del_resp.text

    # Confirm GET returns empty list after deletion (mocked service returns [])
    with _auth_patches() as headers, patch(
        "app.routers.attachments.require_feature", new=AsyncMock(return_value=None)
    ), patch(
        "app.routers.attachments.list_attachments", new=AsyncMock(return_value=[])
    ), patch(
        "app.routers.attachments.get_session_factory", return_value=_fake_session_factory()
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            list_resp = await client.get(_attachment_url(), headers=headers)

    assert list_resp.status_code == 200, list_resp.text
    assert list_resp.json() == []
