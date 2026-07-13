from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.s3 import delete_object, put_object
from app.models.appointment import Appointment
from app.models.appointment_attachment import AppointmentAttachment

_ACCEPTED_CONTENT_TYPES = frozenset(
    ["image/jpeg", "image/png", "application/pdf", "image/tiff", "text/plain"]
)
_MAX_SIZE_BYTES = 64 * 1024 * 1024  # 64 MB


async def _load_appointment(
    session: AsyncSession,
    practice_id: uuid.UUID,
    appointment_id: uuid.UUID,
) -> Appointment:
    appt = await session.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.deleted_at.is_(None),
        )
    )
    if appt is None or appt.practice_id != practice_id:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appt


async def upload_attachment(
    session: AsyncSession,
    *,
    practice_id: uuid.UUID,
    appointment_id: uuid.UUID,
    file_bytes: bytes,
    file_name: str,
    content_type: str,
    attachment_type: str,
    user_sub: str,
) -> AppointmentAttachment:
    if content_type not in _ACCEPTED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "UNSUPPORTED_FILE_TYPE",
                "message": f"Content type {content_type!r} is not accepted",
            },
        )
    if len(file_bytes) > _MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "FILE_TOO_LARGE",
                "message": "File exceeds the 64 MB limit",
            },
        )

    await _load_appointment(session, practice_id, appointment_id)

    attachment_id = uuid.uuid4()
    settings = get_settings()
    s3_key = f"{practice_id}/appointments/{appointment_id}/{attachment_id}/{file_name}"

    put_object(settings.s3_bucket_phi_documents, s3_key, file_bytes, content_type)

    row = AppointmentAttachment(
        id=attachment_id,
        practice_id=practice_id,
        appointment_id=appointment_id,
        s3_key=s3_key,
        file_name=file_name,
        file_size_bytes=len(file_bytes),
        content_type=content_type,
        attachment_type=attachment_type,
        uploaded_by=user_sub,
        last_accessed_by=user_sub,
        last_accessed_at=datetime.now(UTC),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_attachments(
    session: AsyncSession,
    *,
    practice_id: uuid.UUID,
    appointment_id: uuid.UUID,
) -> list[AppointmentAttachment]:
    await _load_appointment(session, practice_id, appointment_id)
    rows = (
        await session.scalars(
            select(AppointmentAttachment).where(
                AppointmentAttachment.appointment_id == appointment_id,
                AppointmentAttachment.practice_id == practice_id,
                AppointmentAttachment.deleted_at.is_(None),
            )
        )
    ).all()
    return list(rows)


async def delete_attachment(
    session: AsyncSession,
    *,
    practice_id: uuid.UUID,
    attachment_id: uuid.UUID,
) -> None:
    row = await session.scalar(
        select(AppointmentAttachment).where(
            AppointmentAttachment.id == attachment_id,
            AppointmentAttachment.practice_id == practice_id,
            AppointmentAttachment.deleted_at.is_(None),
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    settings = get_settings()
    delete_object(settings.s3_bucket_phi_documents, row.s3_key)
    row.deleted_at = datetime.now(UTC)
    await session.commit()
