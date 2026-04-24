from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import get_session_factory
from app.models.appointment import Appointment as AppointmentModel
from app.models.appointment_type import AppointmentType as AppointmentTypeModel
from app.models.operatory import Operatory as OperatoryModel
from app.models.patient import Patient as PatientModel
from app.models.provider import Provider as ProviderModel
from app.schemas.generated import (
    ApiError,
    Appointment,
    CancelAppointment,
    CreateAppointment,
    Error,
    UpdateAppointment,
)
from app.services.reminders import cancel_reminders_for_appointment, stage_reminder_jobs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/appointments", tags=["scheduling"])

_WRITE_ROLES: frozenset[str] = frozenset({"admin", "provider", "front_desk"})


def _err(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}

# ── Status state machine ─────────────────────────────────────────────────────

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "scheduled": frozenset({"confirmed", "cancelled", "no_show"}),
    "confirmed": frozenset({"scheduled", "checked_in", "cancelled", "no_show"}),
    "checked_in": frozenset({"scheduled", "in_chair", "cancelled", "no_show"}),
    "in_chair": frozenset({"scheduled", "completed", "cancelled", "no_show"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
    "no_show": frozenset({"scheduled"}),
}

# Statuses that are "dead" — excluded from conflict detection.
_INACTIVE_STATUSES: frozenset[str] = frozenset({"cancelled", "no_show"})


# ── Guards ────────────────────────────────────────────────────────────────────


def _require_practice_scope(request: Request) -> uuid.UUID:
    practice_id = getattr(request.state.user, "practice_id", None)
    if practice_id is None:
        raise HTTPException(
            status_code=403,
            detail=ApiError(
                error=Error(
                    code="PRACTICE_SCOPE_REQUIRED",
                    message="X-Practice-ID header is required for this endpoint",
                )
            ).model_dump(by_alias=True),
        )
    assert isinstance(practice_id, uuid.UUID)
    return practice_id


def _require_write_role(request: Request) -> None:
    role = getattr(request.state.user, "role", None)
    if role not in _WRITE_ROLES:
        raise HTTPException(
            status_code=403,
            detail=ApiError(
                error=Error(
                    code="INSUFFICIENT_ROLE",
                    message="Your role does not permit this action",
                )
            ).model_dump(by_alias=True),
        )


# ── Conflict detection ───────────────────────────────────────────────────────


async def _check_conflicts(
    session: AsyncSession,
    practice_id: uuid.UUID,
    provider_id: uuid.UUID | None,
    operatory_id: uuid.UUID | None,
    start_time: datetime,
    end_time: datetime,
    exclude_id: uuid.UUID | None = None,
) -> list[dict[str, str]]:
    """Return a list of conflicts [{type, id, resource_id}] for overlapping appointments."""
    conflicts: list[dict[str, str]] = []

    base_filters = [
        AppointmentModel.practice_id == practice_id,
        AppointmentModel.deleted_at.is_(None),
        AppointmentModel.status.notin_(_INACTIVE_STATUSES),
        # Overlap condition: existing.start < new.end AND existing.end > new.start
        AppointmentModel.start_time < end_time,
        AppointmentModel.end_time > start_time,
    ]

    if exclude_id is not None:
        base_filters.append(AppointmentModel.id != exclude_id)

    # Check provider conflicts
    if provider_id is not None:
        provider_rows = (
            await session.scalars(
                select(AppointmentModel).where(
                    *base_filters,
                    AppointmentModel.provider_id == provider_id,
                )
            )
        ).all()
        for row in provider_rows:
            conflicts.append({
                "type": "provider",
                "appointmentId": str(row.id),
                "resourceId": str(provider_id),
            })

    # Check operatory conflicts
    if operatory_id is not None:
        operatory_rows = (
            await session.scalars(
                select(AppointmentModel).where(
                    *base_filters,
                    AppointmentModel.operatory_id == operatory_id,
                )
            )
        ).all()
        for row in operatory_rows:
            conflicts.append({
                "type": "operatory",
                "appointmentId": str(row.id),
                "resourceId": str(operatory_id),
            })

    return conflicts


def _validate_status_transition(current: str, proposed: str) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if proposed not in allowed:
        raise HTTPException(
            status_code=422,
            detail=ApiError(
                error=Error(
                    code="INVALID_STATUS_TRANSITION",
                    message=f"Cannot transition from '{current}' to '{proposed}'",
                    details={"currentStatus": current, "proposedStatus": proposed},
                )
            ).model_dump(by_alias=True),
        )


# ── Serialisation ─────────────────────────────────────────────────────────────


def _row_to_schema(row: AppointmentModel) -> Appointment:
    patient_name: str | None = None
    if row.patient is not None:
        patient_name = f"{row.patient.first_name} {row.patient.last_name}"

    provider_name: str | None = None
    if row.provider is not None:
        provider_name = row.provider.full_name

    operatory_name: str | None = None
    if row.operatory is not None:
        operatory_name = row.operatory.name

    appt_type_name: str | None = None
    appt_type_color: str | None = None
    if row.appointment_type is not None:
        appt_type_name = row.appointment_type.name
        appt_type_color = row.appointment_type.color

    return Appointment(
        id=row.id,
        practiceId=row.practice_id,
        patientId=row.patient_id,
        providerId=row.provider_id,
        operatoryId=row.operatory_id,
        appointmentTypeId=row.appointment_type_id,
        startTime=row.start_time,
        endTime=row.end_time,
        status=row.status,  # type: ignore[arg-type]
        notes=row.notes,
        cancellationReason=row.cancellation_reason,
        patientName=patient_name,
        providerName=provider_name,
        operatoryName=operatory_name,
        appointmentTypeName=appt_type_name,
        appointmentTypeColor=appt_type_color,
        createdAt=row.created_at,
        updatedAt=row.updated_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("", response_model=list[Appointment])
async def list_appointments(
    request: Request,
    provider_id: uuid.UUID | None = None,
    operatory_id: uuid.UUID | None = None,
    status: str | None = None,
) -> list[Appointment]:
    practice_id = _require_practice_scope(request)

    filters = [
        AppointmentModel.practice_id == practice_id,
        AppointmentModel.deleted_at.is_(None),
    ]

    if provider_id is not None:
        filters.append(AppointmentModel.provider_id == provider_id)
    if operatory_id is not None:
        filters.append(AppointmentModel.operatory_id == operatory_id)
    if status is not None:
        filters.append(AppointmentModel.status == status)

    async with get_session_factory()() as session:
        rows = (
            await session.scalars(
                select(AppointmentModel)
                .where(*filters)
                .options(
                    selectinload(AppointmentModel.patient),
                    selectinload(AppointmentModel.provider),
                    selectinload(AppointmentModel.operatory),
                    selectinload(AppointmentModel.appointment_type),
                )
                .order_by(AppointmentModel.start_time.asc())
            )
        ).all()

    return [_row_to_schema(r) for r in rows]


@router.get("/{appointment_id}", response_model=Appointment)
async def get_appointment(
    appointment_id: uuid.UUID,
    request: Request,
) -> Appointment:
    practice_id = _require_practice_scope(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(AppointmentModel)
            .where(
                AppointmentModel.id == appointment_id,
                AppointmentModel.practice_id == practice_id,
                AppointmentModel.deleted_at.is_(None),
            )
            .options(
                selectinload(AppointmentModel.patient),
                selectinload(AppointmentModel.provider),
                selectinload(AppointmentModel.operatory),
                selectinload(AppointmentModel.appointment_type),
            )
        )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "APPOINTMENT_NOT_FOUND", "message": "Appointment not found"}},
        )

    return _row_to_schema(row)


@router.post("", status_code=201, response_model=Appointment)
async def create_appointment(
    body: CreateAppointment,
    request: Request,
) -> Appointment:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        # Validate FK references belong to this practice
        patient = await session.scalar(
            select(PatientModel).where(
                PatientModel.id == body.patient_id,
                PatientModel.practice_id == practice_id,
                PatientModel.deleted_at.is_(None),
            )
        )
        if patient is None:
            raise HTTPException(
                status_code=404,
                detail=_err("PATIENT_NOT_FOUND", "Patient not found in this practice"),
            )

        provider = await session.scalar(
            select(ProviderModel).where(
                ProviderModel.id == body.provider_id,
                ProviderModel.practice_id == practice_id,
                ProviderModel.deleted_at.is_(None),
            )
        )
        if provider is None:
            raise HTTPException(
                status_code=404,
                detail=_err("PROVIDER_NOT_FOUND", "Provider not found in this practice"),
            )

        operatory = await session.scalar(
            select(OperatoryModel).where(
                OperatoryModel.id == body.operatory_id,
                OperatoryModel.practice_id == practice_id,
                OperatoryModel.deleted_at.is_(None),
            )
        )
        if operatory is None:
            raise HTTPException(
                status_code=404,
                detail=_err("OPERATORY_NOT_FOUND", "Operatory not found in this practice"),
            )

        if body.appointment_type_id is not None:
            appt_type = await session.scalar(
                select(AppointmentTypeModel).where(
                    AppointmentTypeModel.id == body.appointment_type_id,
                    AppointmentTypeModel.practice_id == practice_id,
                    AppointmentTypeModel.deleted_at.is_(None),
                )
            )
            if appt_type is None:
                raise HTTPException(
                    status_code=404,
                    detail=_err(
                        "APPOINTMENT_TYPE_NOT_FOUND",
                        "Appointment type not found in this practice",
                    ),
                )

        # Conflict detection
        conflicts = await _check_conflicts(
            session,
            practice_id=practice_id,
            provider_id=body.provider_id,
            operatory_id=body.operatory_id,
            start_time=body.start_time,
            end_time=body.end_time,
        )
        if conflicts:
            raise HTTPException(
                status_code=409,
                detail=ApiError(
                    error=Error(
                        code="SCHEDULING_CONFLICT",
                        message="Appointment conflicts with existing schedule",
                        details={"conflicts": conflicts},
                    )
                ).model_dump(by_alias=True),
            )

        row = AppointmentModel(
            id=uuid.uuid4(),
            practice_id=practice_id,
            patient_id=body.patient_id,
            provider_id=body.provider_id,
            operatory_id=body.operatory_id,
            appointment_type_id=body.appointment_type_id,
            start_time=body.start_time,
            end_time=body.end_time,
            status="scheduled",
            notes=body.notes,
        )

        session.add(row)
        stage_reminder_jobs(session, row)
        await session.commit()

        # Re-fetch with relationships for the response
        fetched = await session.scalar(
            select(AppointmentModel)
            .where(AppointmentModel.id == row.id)
            .options(
                selectinload(AppointmentModel.patient),
                selectinload(AppointmentModel.provider),
                selectinload(AppointmentModel.operatory),
                selectinload(AppointmentModel.appointment_type),
            )
        )
        assert fetched is not None

    return _row_to_schema(fetched)


@router.patch("/{appointment_id}", response_model=Appointment)
async def update_appointment(
    appointment_id: uuid.UUID,
    body: UpdateAppointment,
    request: Request,
) -> Appointment:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(AppointmentModel).where(
                AppointmentModel.id == appointment_id,
                AppointmentModel.practice_id == practice_id,
                AppointmentModel.deleted_at.is_(None),
            )
        )

        if row is None:
            raise HTTPException(
                status_code=404,
                detail=_err("APPOINTMENT_NOT_FOUND", "Appointment not found"),
            )

        provided = body.model_fields_set
        time_changed = bool(provided & {"start_time", "end_time"})

        # Validate status transition if status is being changed
        if "status" in provided and body.status is not None:
            _validate_status_transition(row.status, body.status)

        # Track whether scheduling fields changed (need conflict re-check)
        scheduling_fields_changed = bool(
            provided & {"start_time", "end_time", "provider_id", "operatory_id"}
        )


        # Validate FK references if they're being changed
        if "provider_id" in provided and body.provider_id is not None:
            provider = await session.scalar(
                select(ProviderModel).where(
                    ProviderModel.id == body.provider_id,
                    ProviderModel.practice_id == practice_id,
                    ProviderModel.deleted_at.is_(None),
                )
            )
            if provider is None:
                raise HTTPException(
                    status_code=404,
                    detail=_err("PROVIDER_NOT_FOUND", "Provider not found in this practice"),
                )

        if "operatory_id" in provided and body.operatory_id is not None:
            operatory = await session.scalar(
                select(OperatoryModel).where(
                    OperatoryModel.id == body.operatory_id,
                    OperatoryModel.practice_id == practice_id,
                    OperatoryModel.deleted_at.is_(None),
                )
            )
            if operatory is None:
                raise HTTPException(
                    status_code=404,
                    detail=_err("OPERATORY_NOT_FOUND", "Operatory not found in this practice"),
                )

        if "patient_id" in provided and body.patient_id is not None:
            patient = await session.scalar(
                select(PatientModel).where(
                    PatientModel.id == body.patient_id,
                    PatientModel.practice_id == practice_id,
                    PatientModel.deleted_at.is_(None),
                )
            )
            if patient is None:
                raise HTTPException(
                    status_code=404,
                    detail=_err("PATIENT_NOT_FOUND", "Patient not found in this practice"),
                )

        if "appointment_type_id" in provided and body.appointment_type_id is not None:
            appt_type = await session.scalar(
                select(AppointmentTypeModel).where(
                    AppointmentTypeModel.id == body.appointment_type_id,
                    AppointmentTypeModel.practice_id == practice_id,
                    AppointmentTypeModel.deleted_at.is_(None),
                )
            )
            if appt_type is None:
                raise HTTPException(
                    status_code=404,
                    detail=_err(
                        "APPOINTMENT_TYPE_NOT_FOUND",
                        "Appointment type not found in this practice",
                    ),
                )

        # Apply updates
        field_map: dict[str, str] = {
            "patient_id": "patient_id",
            "provider_id": "provider_id",
            "operatory_id": "operatory_id",
            "appointment_type_id": "appointment_type_id",
            "start_time": "start_time",
            "end_time": "end_time",
            "status": "status",
            "notes": "notes",
            "cancellation_reason": "cancellation_reason",
        }

        for schema_field, model_field in field_map.items():
            if schema_field in provided:
                setattr(row, model_field, getattr(body, schema_field))

        # Re-check conflicts if scheduling fields changed
        if scheduling_fields_changed:
            conflicts = await _check_conflicts(
                session,
                practice_id=practice_id,
                provider_id=row.provider_id,
                operatory_id=row.operatory_id,
                start_time=row.start_time,
                end_time=row.end_time,
                exclude_id=row.id,
            )
            if conflicts:
                raise HTTPException(
                    status_code=409,
                    detail=ApiError(
                        error=Error(
                            code="SCHEDULING_CONFLICT",
                            message="Rescheduled appointment conflicts with existing schedule",
                            details={"conflicts": conflicts},
                        )
                    ).model_dump(by_alias=True),
                )

        # Update reminders: terminal status cancels them; time change reschedules them.
        if row.status in ("cancelled", "no_show"):
            await cancel_reminders_for_appointment(session, appointment_id)
        elif time_changed:
            await cancel_reminders_for_appointment(session, appointment_id)
            stage_reminder_jobs(session, row)

        await session.commit()

        # Re-fetch with relationships
        fetched = await session.scalar(
            select(AppointmentModel)
            .where(AppointmentModel.id == appointment_id)
            .options(
                selectinload(AppointmentModel.patient),
                selectinload(AppointmentModel.provider),
                selectinload(AppointmentModel.operatory),
                selectinload(AppointmentModel.appointment_type),
            )
        )
        assert fetched is not None

    return _row_to_schema(fetched)


@router.delete("/{appointment_id}", status_code=204)
async def cancel_appointment(
    appointment_id: uuid.UUID,
    request: Request,
    body: CancelAppointment | None = None,
) -> None:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(AppointmentModel).where(
                AppointmentModel.id == appointment_id,
                AppointmentModel.practice_id == practice_id,
                AppointmentModel.deleted_at.is_(None),
            )
        )

        if row is None:
            raise HTTPException(
                status_code=404,
                detail=_err("APPOINTMENT_NOT_FOUND", "Appointment not found"),
            )

        # Cannot cancel a terminal-state appointment
        if row.status in ("completed", "cancelled", "no_show"):
            raise HTTPException(
                status_code=422,
                detail=ApiError(
                    error=Error(
                        code="INVALID_STATUS_TRANSITION",
                        message=f"Cannot cancel an appointment with status '{row.status}'",
                    )
                ).model_dump(by_alias=True),
            )

        row.status = "cancelled"
        if body is not None and body.cancellation_reason is not None:
            row.cancellation_reason = body.cancellation_reason
        row.deleted_at = datetime.now(UTC)
        await cancel_reminders_for_appointment(session, appointment_id)
        await session.commit()
