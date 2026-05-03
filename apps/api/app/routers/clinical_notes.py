from __future__ import annotations

import base64
import json
import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.models.appointment import Appointment as AppointmentModel
from app.models.clinical_note import ClinicalNote as ClinicalNoteModel
from app.models.patient import Patient as PatientModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import (
    ApiError,
    ClinicalNote,
    ClinicalNoteListResponse,
    ClinicalNoteSummary,
    CreateClinicalNote,
    Error,
    TemplateType,
    UpdateClinicalNote,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/patients/{patient_id}/clinical-notes",
    tags=["clinical-notes"],
)

_MAX_LIMIT = 100
_DEFAULT_LIMIT = 20


# ── Cursor helpers ────────────────────────────────────────────────────────────


def _encode_cursor(visit_date: date, note_id: uuid.UUID) -> str:
    payload = {"d": visit_date.isoformat(), "i": str(note_id)}
    return base64.b64encode(json.dumps(payload).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[date, uuid.UUID] | None:
    try:
        payload = json.loads(base64.b64decode(cursor).decode())
        return date.fromisoformat(payload["d"]), uuid.UUID(payload["i"])
    except Exception:
        return None


# ── Serialisation helpers ─────────────────────────────────────────────────────


def _row_to_schema(row: ClinicalNoteModel) -> ClinicalNote:
    return ClinicalNote(
        id=row.id,
        practiceId=row.practice_id,
        patientId=row.patient_id,
        appointmentId=row.appointment_id,
        providerId=row.provider_id,
        visitDate=row.visit_date,
        chiefComplaint=row.chief_complaint,
        anesthesia=row.anesthesia,
        patientTolerance=row.patient_tolerance,
        complications=row.complications,
        treatmentRendered=row.treatment_rendered,
        nextVisitPlan=row.next_visit_plan,
        notes=row.notes,
        templateType=row.template_type,
        isSigned=row.is_signed,
        signedAt=row.signed_at.replace(tzinfo=UTC) if row.signed_at else None,
        signedByProviderId=row.signed_by_provider_id,
        createdAt=row.created_at.replace(tzinfo=UTC),
        updatedAt=row.updated_at.replace(tzinfo=UTC),
    )


def _row_to_summary(row: ClinicalNoteModel) -> ClinicalNoteSummary:
    return ClinicalNoteSummary(
        id=row.id,
        patientId=row.patient_id,
        providerId=row.provider_id,
        appointmentId=row.appointment_id,
        visitDate=row.visit_date,
        treatmentRendered=row.treatment_rendered,
        templateType=row.template_type,
        isSigned=row.is_signed,
        signedAt=row.signed_at.replace(tzinfo=UTC) if row.signed_at else None,
        createdAt=row.created_at.replace(tzinfo=UTC),
        updatedAt=row.updated_at.replace(tzinfo=UTC),
    )


async def _phi_audit(
    session: AsyncSession,
    row_id: uuid.UUID,
    user_sub: str | None,
) -> None:
    await session.execute(
        update(ClinicalNoteModel)
        .where(ClinicalNoteModel.id == row_id)
        .values(
            last_accessed_by=user_sub,
            last_accessed_at=datetime.now(UTC),
        )
        .execution_options(synchronize_session=False)
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("", response_model=ClinicalNoteListResponse)
async def list_clinical_notes(
    patient_id: uuid.UUID,
    request: Request,
    limit: int = _DEFAULT_LIMIT,
    cursor: str | None = None,
    appointment_id: uuid.UUID | None = None,
) -> ClinicalNoteListResponse:
    practice_id = _require_practice_scope(request)
    user_sub = getattr(request.state.user, "sub", None)
    limit = min(max(limit, 1), _MAX_LIMIT)

    async with get_session_factory()() as session:
        q = select(ClinicalNoteModel).where(
            ClinicalNoteModel.patient_id == patient_id,
            ClinicalNoteModel.practice_id == practice_id,
            ClinicalNoteModel.deleted_at.is_(None),
        )

        if appointment_id is not None:
            q = q.where(ClinicalNoteModel.appointment_id == appointment_id)

        if cursor is not None:
            decoded = _decode_cursor(cursor)
            if decoded is not None:
                cursor_date, cursor_id = decoded
                q = q.where(
                    or_(
                        ClinicalNoteModel.visit_date < cursor_date,
                        and_(
                            ClinicalNoteModel.visit_date == cursor_date,
                            ClinicalNoteModel.id < cursor_id,
                        ),
                    )
                )

        q = (
            q.order_by(ClinicalNoteModel.visit_date.desc(), ClinicalNoteModel.id.desc())
            .limit(limit + 1)
        )

        rows = (await session.scalars(q)).all()

        has_more = len(rows) > limit
        items = list(rows[:limit])

        next_cursor: str | None = None
        if has_more and items:
            last = items[-1]
            next_cursor = _encode_cursor(last.visit_date, last.id)

        for item in items:
            await _phi_audit(session, item.id, user_sub)
        if items:
            await session.commit()

    return ClinicalNoteListResponse(
        items=[_row_to_summary(r) for r in items],
        nextCursor=next_cursor,
        hasMore=has_more,
    )


@router.post("", status_code=201, response_model=ClinicalNote)
async def create_clinical_note(
    patient_id: uuid.UUID,
    body: CreateClinicalNote,
    request: Request,
) -> ClinicalNote:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        patient = await session.scalar(
            select(PatientModel).where(
                PatientModel.id == patient_id,
                PatientModel.practice_id == practice_id,
                PatientModel.deleted_at.is_(None),
            )
        )
        if patient is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="PATIENT_NOT_FOUND", message="Patient not found")
                ).model_dump(by_alias=True),
            )

        if body.appointment_id is not None:
            appt = await session.scalar(
                select(AppointmentModel).where(
                    AppointmentModel.id == body.appointment_id,
                    AppointmentModel.practice_id == practice_id,
                    AppointmentModel.patient_id == patient_id,
                )
            )
            if appt is None:
                raise HTTPException(
                    status_code=400,
                    detail=ApiError(
                        error=Error(
                            code="INVALID_APPOINTMENT",
                            message="Appointment does not belong to this patient",
                        )
                    ).model_dump(by_alias=True),
                )

        row = ClinicalNoteModel(
            id=uuid.uuid4(),
            practice_id=practice_id,
            patient_id=patient_id,
            appointment_id=body.appointment_id,
            provider_id=body.provider_id,
            visit_date=body.visit_date,
            chief_complaint=body.chief_complaint,
            anesthesia=body.anesthesia,
            patient_tolerance=body.patient_tolerance,
            complications=body.complications,
            treatment_rendered=body.treatment_rendered,
            next_visit_plan=body.next_visit_plan,
            notes=body.notes,
            template_type=body.template_type,
            is_signed=False,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)

    logger.info(
        "Clinical note created: patient_id=%s note_id=%s provider_id=%s",
        patient_id,
        row.id,
        body.provider_id,
    )

    return _row_to_schema(row)


@router.get("/{note_id}", response_model=ClinicalNote)
async def get_clinical_note(
    patient_id: uuid.UUID,
    note_id: uuid.UUID,
    request: Request,
) -> ClinicalNote:
    practice_id = _require_practice_scope(request)
    user_sub = getattr(request.state.user, "sub", None)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(ClinicalNoteModel).where(
                ClinicalNoteModel.id == note_id,
                ClinicalNoteModel.patient_id == patient_id,
                ClinicalNoteModel.practice_id == practice_id,
                ClinicalNoteModel.deleted_at.is_(None),
            )
        )
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="NOTE_NOT_FOUND", message="Clinical note not found")
                ).model_dump(by_alias=True),
            )

        await _phi_audit(session, row.id, user_sub)
        await session.commit()

    return _row_to_schema(row)


@router.patch("/{note_id}", response_model=ClinicalNote)
async def update_clinical_note(
    patient_id: uuid.UUID,
    note_id: uuid.UUID,
    body: UpdateClinicalNote,
    request: Request,
) -> ClinicalNote:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(ClinicalNoteModel)
            .where(
                ClinicalNoteModel.id == note_id,
                ClinicalNoteModel.patient_id == patient_id,
                ClinicalNoteModel.practice_id == practice_id,
                ClinicalNoteModel.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="NOTE_NOT_FOUND", message="Clinical note not found")
                ).model_dump(by_alias=True),
            )

        if row.is_signed:
            raise HTTPException(
                status_code=409,
                detail=ApiError(
                    error=Error(
                        code="NOTE_ALREADY_SIGNED",
                        message="Signed notes cannot be edited",
                    )
                ).model_dump(by_alias=True),
            )

        update_data: dict[str, Any] = {}
        if body.chief_complaint is not None:
            update_data["chief_complaint"] = body.chief_complaint
        if body.anesthesia is not None:
            update_data["anesthesia"] = body.anesthesia
        if body.patient_tolerance is not None:
            update_data["patient_tolerance"] = body.patient_tolerance
        if body.complications is not None:
            update_data["complications"] = body.complications
        if body.treatment_rendered is not None:
            update_data["treatment_rendered"] = body.treatment_rendered
        if body.next_visit_plan is not None:
            update_data["next_visit_plan"] = body.next_visit_plan
        if body.notes is not None:
            update_data["notes"] = body.notes
        if body.template_type is not None:
            update_data["template_type"] = body.template_type

        for key, value in update_data.items():
            setattr(row, key, value)
        row.updated_at = datetime.now(UTC)

        await session.commit()
        await session.refresh(row)

    return _row_to_schema(row)


@router.post("/{note_id}/sign", response_model=ClinicalNote)
async def sign_clinical_note(
    patient_id: uuid.UUID,
    note_id: uuid.UUID,
    request: Request,
) -> ClinicalNote:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_id = getattr(request.state.user, "user_id", None)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(ClinicalNoteModel)
            .where(
                ClinicalNoteModel.id == note_id,
                ClinicalNoteModel.patient_id == patient_id,
                ClinicalNoteModel.practice_id == practice_id,
                ClinicalNoteModel.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="NOTE_NOT_FOUND", message="Clinical note not found")
                ).model_dump(by_alias=True),
            )

        if row.is_signed:
            raise HTTPException(
                status_code=409,
                detail=ApiError(
                    error=Error(
                        code="NOTE_ALREADY_SIGNED",
                        message="Note has already been signed",
                    )
                ).model_dump(by_alias=True),
            )

        now = datetime.now(UTC)
        row.is_signed = True
        row.signed_at = now
        row.signed_by_provider_id = user_id
        row.updated_at = now

        await session.commit()
        await session.refresh(row)

    logger.info(
        "Clinical note signed: patient_id=%s note_id=%s user_id=%s",
        patient_id,
        note_id,
        user_id,
    )

    return _row_to_schema(row)
