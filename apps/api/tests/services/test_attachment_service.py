from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


# ── Minimal stub ORM rows ──────────────────────────────────────────────────────

class _FakeAppt:
    def __init__(self, appt_id: uuid.UUID, practice_id: uuid.UUID):
        self.id = appt_id
        self.practice_id = practice_id
        self.deleted_at = None


# ── upload_attachment ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_attachment_happy_path():
    from unittest.mock import AsyncMock

    from app.services.attachments.service import upload_attachment

    practice_id = uuid.uuid4()
    appointment_id = uuid.uuid4()
    file_bytes = b"fake-xray-data"

    mock_session = MagicMock()
    mock_session.scalar = AsyncMock(return_value=_FakeAppt(appointment_id, practice_id))
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    with patch("app.services.attachments.service.put_object") as mock_put, \
         patch("app.services.attachments.service.get_settings") as mock_cfg:
        mock_cfg.return_value.s3_bucket_phi_documents = "test-bucket"
        result = await upload_attachment(
            mock_session,
            practice_id=practice_id,
            appointment_id=appointment_id,
            file_bytes=file_bytes,
            file_name="xray.jpg",
            content_type="image/jpeg",
            attachment_type="xray",
            user_sub="user-123",
        )

    mock_put.assert_called_once()
    call_kwargs = mock_put.call_args
    assert call_kwargs[0][0] == "test-bucket"
    assert "image/jpeg" in call_kwargs[0][3]
    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_attachment_unsupported_content_type_raises():
    from unittest.mock import AsyncMock

    from fastapi import HTTPException

    from app.services.attachments.service import upload_attachment

    practice_id = uuid.uuid4()
    appointment_id = uuid.uuid4()

    mock_session = MagicMock()
    mock_session.scalar = AsyncMock(return_value=_FakeAppt(appointment_id, practice_id))

    with pytest.raises(HTTPException) as exc_info:
        await upload_attachment(
            mock_session,
            practice_id=practice_id,
            appointment_id=appointment_id,
            file_bytes=b"data",
            file_name="doc.docx",
            content_type="application/msword",
            attachment_type="other",
            user_sub="user-123",
        )
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_upload_attachment_wrong_practice_raises():
    from unittest.mock import AsyncMock

    from fastapi import HTTPException

    from app.services.attachments.service import upload_attachment

    practice_id = uuid.uuid4()
    other_practice_id = uuid.uuid4()
    appointment_id = uuid.uuid4()

    mock_session = MagicMock()
    # Appointment belongs to a different practice
    mock_session.scalar = AsyncMock(
        return_value=_FakeAppt(appointment_id, other_practice_id)
    )

    with pytest.raises(HTTPException) as exc_info:
        await upload_attachment(
            mock_session,
            practice_id=practice_id,
            appointment_id=appointment_id,
            file_bytes=b"data",
            file_name="xray.jpg",
            content_type="image/jpeg",
            attachment_type="xray",
            user_sub="user-123",
        )
    assert exc_info.value.status_code == 404
