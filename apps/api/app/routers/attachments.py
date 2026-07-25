from __future__ import annotations

import uuid
from datetime import UTC

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile

from app.core.db import get_session_factory
from app.core.features import require_feature
from app.models.appointment_attachment import AppointmentAttachment as AttachmentModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import ApiError, AppointmentAttachment, AttachmentType, Error
from app.services.attachments.service import (
    delete_attachment,
    list_attachments,
    upload_attachment,
)

router = APIRouter(prefix="/api/v1", tags=["attachments"])

_FEATURE = "claims_submission"


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=ApiError(error=Error(code=code, message=message)).model_dump(by_alias=True),
    )


def _to_schema(row: AttachmentModel) -> AppointmentAttachment:
    return AppointmentAttachment(
        id=row.id,
        practiceId=row.practice_id,
        appointmentId=row.appointment_id,
        s3Key=row.s3_key,
        fileName=row.file_name,
        fileSizeBytes=row.file_size_bytes,
        contentType=row.content_type,
        attachmentType=AttachmentType(row.attachment_type),
        uploadedBy=row.uploaded_by,
        createdAt=row.created_at.replace(tzinfo=UTC),
    )


@router.post(
    "/appointments/{appointment_id}/attachments",
    status_code=201,
    response_model=AppointmentAttachment,
)
async def create_attachment(
    appointment_id: uuid.UUID,
    file: UploadFile,
    request: Request,
    attachment_type: str = Form(...),
) -> AppointmentAttachment:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_sub = getattr(request.state.user, "sub", "unknown")

    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)

        file_bytes = await file.read()
        content_type = file.content_type or "application/octet-stream"

        row = await upload_attachment(
            session,
            practice_id=practice_id,
            appointment_id=appointment_id,
            file_bytes=file_bytes,
            file_name=file.filename or "attachment",
            content_type=content_type,
            attachment_type=attachment_type,
            user_sub=user_sub,
        )
    return _to_schema(row)


@router.get(
    "/appointments/{appointment_id}/attachments",
    response_model=list[AppointmentAttachment],
)
async def get_attachments(
    appointment_id: uuid.UUID,
    request: Request,
) -> list[AppointmentAttachment]:
    practice_id = _require_practice_scope(request)

    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        rows = await list_attachments(
            session,
            practice_id=practice_id,
            appointment_id=appointment_id,
        )
    return [_to_schema(r) for r in rows]


@router.delete(
    "/appointments/{appointment_id}/attachments/{attachment_id}",
    status_code=204,
)
async def remove_attachment(
    appointment_id: uuid.UUID,
    attachment_id: uuid.UUID,
    request: Request,
) -> None:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        await delete_attachment(session, practice_id=practice_id, attachment_id=attachment_id)
