from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
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
    s3_key = call_kwargs[0][1]
    assert s3_key.startswith(f"{practice_id}/appointments/{appointment_id}/")
    assert s3_key.endswith("/xray.jpg")
    assert "image/jpeg" in call_kwargs[0][3]
    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()
    assert result is not None


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


# ── generate_perio_narrative ───────────────────────────────────────────────────


@dataclass
class _FakePerioChart:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    appointment_id: uuid.UUID = field(default_factory=uuid.uuid4)
    patient_id: uuid.UUID = field(default_factory=uuid.uuid4)
    chart_date: date = field(default_factory=date.today)
    notes: str | None = None


class _FakeReading:
    def __init__(self, tooth: str, site: str, depth: int):
        self.tooth_number = tooth
        self.site = site
        self.probing_depth_mm = depth
        self.recession_mm = 0
        self.bleeding = False
        self.suppuration = False
        self.furcation = None
        self.mobility = None


@dataclass
class _FakeProc:
    procedure_code: str = "D4341"
    deleted_at: None = None


async def test_generate_perio_narrative_creates_attachment():
    from unittest.mock import AsyncMock, MagicMock

    from app.services.attachments.service import generate_perio_narrative

    practice_id = uuid.uuid4()
    appointment_id = uuid.uuid4()
    chart_id = uuid.uuid4()

    chart = _FakePerioChart(id=chart_id, appointment_id=appointment_id)
    readings = [_FakeReading("3", "b", 4), _FakeReading("3", "mb", 3)]
    proc = _FakeProc(procedure_code="D4341")

    mock_session = MagicMock()

    # scalar calls: (1) check existing perio_narrative → None, (2) load chart → chart
    mock_session.scalar = AsyncMock(side_effect=[None, chart])

    # scalars calls: (1) procedures → [proc], (2) readings → readings
    mock_scalars_result_procs = MagicMock()
    mock_scalars_result_procs.all.return_value = [proc]
    mock_scalars_result_readings = MagicMock()
    mock_scalars_result_readings.all.return_value = readings
    mock_session.scalars = AsyncMock(
        side_effect=[mock_scalars_result_procs, mock_scalars_result_readings]
    )

    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    with patch("app.services.attachments.service.put_object") as mock_put, \
         patch("app.services.attachments.service.get_settings") as mock_cfg:
        mock_cfg.return_value.s3_bucket_phi_documents = "test-bucket"
        result = await generate_perio_narrative(
            mock_session,
            practice_id=practice_id,
            appointment_id=appointment_id,
        )

    assert result is not None
    mock_put.assert_called_once()
    written_bytes = mock_put.call_args[0][2]
    assert b"PERIODONTAL" in written_bytes
    assert b"D4341" in written_bytes
    mock_session.add.assert_called_once()


async def test_generate_perio_narrative_no_perio_procedures_returns_none():
    from unittest.mock import AsyncMock, MagicMock

    from app.services.attachments.service import generate_perio_narrative

    mock_session = MagicMock()
    mock_scalars_result = MagicMock()
    mock_scalars_result.all.return_value = [_FakeProc("D2140")]
    mock_session.scalars = AsyncMock(return_value=mock_scalars_result)

    result = await generate_perio_narrative(
        mock_session,
        practice_id=uuid.uuid4(),
        appointment_id=uuid.uuid4(),
    )
    assert result is None


async def test_generate_perio_narrative_idempotent():
    """Second call returns existing row without writing a new S3 object."""
    from unittest.mock import AsyncMock, MagicMock

    from app.models.appointment_attachment import AppointmentAttachment
    from app.services.attachments.service import generate_perio_narrative

    practice_id = uuid.uuid4()
    appointment_id = uuid.uuid4()

    # Simulate an existing perio_narrative row using a plain mock so we
    # don't have to fight SQLAlchemy's ORM initialisation machinery.
    existing = MagicMock(spec=AppointmentAttachment)
    existing.id = uuid.uuid4()
    existing.attachment_type = "perio_narrative"

    mock_session = MagicMock()
    # scalars: procedure query returns [D4341 proc]
    mock_scalars_result = MagicMock()
    mock_scalars_result.all.return_value = [_FakeProc("D4341")]
    mock_session.scalars = AsyncMock(return_value=mock_scalars_result)
    # scalar: existing narrative found
    mock_session.scalar = AsyncMock(return_value=existing)

    with patch("app.services.attachments.service.put_object") as mock_put:
        result = await generate_perio_narrative(
            mock_session,
            practice_id=practice_id,
            appointment_id=appointment_id,
        )

    assert result is existing
    mock_put.assert_not_called()
