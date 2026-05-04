from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.models.appointment import Appointment as AppointmentModel
from app.models.patient import Patient as PatientModel
from app.models.tooth_condition import ToothCondition as ToothConditionModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import (
    ApiError,
    ConditionType,
    CreateToothCondition,
    Error,
    NotationSystem,
    ToothChartResponse,
    ToothCondition,
    ToothConditionStatus,
    UpdateToothCondition,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/patients/{patient_id}/tooth-chart",
    tags=["tooth-chart"],
)


# ── Serialisation ─────────────────────────────────────────────────────────────


def _row_to_schema(row: ToothConditionModel) -> ToothCondition:
    return ToothCondition(
        id=row.id,
        practiceId=row.practice_id,
        patientId=row.patient_id,
        toothNumber=row.tooth_number,
        notationSystem=NotationSystem(row.notation_system),
        conditionType=ConditionType(row.condition_type),
        surface=row.surface,
        material=row.material,
        notes=row.notes,
        status=ToothConditionStatus(row.status),  # type: ignore[arg-type]
        recordedAt=row.recorded_at,
        recordedBy=row.recorded_by,
        appointmentId=row.appointment_id,
        createdAt=row.created_at.replace(tzinfo=UTC),
        updatedAt=row.updated_at.replace(tzinfo=UTC),
    )


async def _phi_audit(
    session: AsyncSession,
    row_id: uuid.UUID,
    user_sub: str | None,
) -> None:
    await session.execute(
        update(ToothConditionModel)
        .where(ToothConditionModel.id == row_id)
        .values(
            last_accessed_by=user_sub,
            last_accessed_at=datetime.now(UTC),
        )
        .execution_options(synchronize_session=False)
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("", response_model=ToothChartResponse)
async def get_tooth_chart(
    patient_id: uuid.UUID,
    request: Request,
    as_of_date: date | None = None,
) -> ToothChartResponse:
    practice_id = _require_practice_scope(request)
    user_sub = getattr(request.state.user, "sub", None)

    async with get_session_factory()() as session:
        q = select(ToothConditionModel).where(
            ToothConditionModel.patient_id == patient_id,
            ToothConditionModel.practice_id == practice_id,
            ToothConditionModel.deleted_at.is_(None),
        )

        if as_of_date is not None:
            q = q.where(ToothConditionModel.recorded_at <= as_of_date)

        q = q.order_by(ToothConditionModel.recorded_at.asc(), ToothConditionModel.id.asc())
        rows = (await session.scalars(q)).all()

        for row in rows:
            await _phi_audit(session, row.id, user_sub)
        if rows:
            await session.commit()

    conditions = [_row_to_schema(r).model_dump(by_alias=True) for r in rows]
    return ToothChartResponse(conditions=conditions)  # type: ignore[arg-type]


@router.post("/conditions", status_code=201, response_model=ToothCondition)
async def add_tooth_condition(
    patient_id: uuid.UUID,
    body: CreateToothCondition,
    request: Request,
) -> ToothCondition:
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

        row = ToothConditionModel(
            id=uuid.uuid4(),
            practice_id=practice_id,
            patient_id=patient_id,
            tooth_number=body.tooth_number,
            notation_system=body.notation_system or "universal",
            condition_type=body.condition_type,
            surface=body.surface,
            material=body.material,
            notes=body.notes,
            status=body.status or "existing",
            recorded_at=body.recorded_at,
            recorded_by=body.recorded_by,
            appointment_id=body.appointment_id,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)

    logger.info(
        "Tooth condition added: patient_id=%s condition_id=%s tooth=%s type=%s",
        patient_id,
        row.id,
        body.tooth_number,
        body.condition_type,
    )

    return _row_to_schema(row)


@router.patch("/conditions/{condition_id}", response_model=ToothCondition)
async def update_tooth_condition(
    patient_id: uuid.UUID,
    condition_id: uuid.UUID,
    body: UpdateToothCondition,
    request: Request,
) -> ToothCondition:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(ToothConditionModel)
            .where(
                ToothConditionModel.id == condition_id,
                ToothConditionModel.patient_id == patient_id,
                ToothConditionModel.practice_id == practice_id,
                ToothConditionModel.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="CONDITION_NOT_FOUND", message="Tooth condition not found")
                ).model_dump(by_alias=True),
            )

        update_data: dict[str, Any] = {}
        if body.status is not None:
            update_data["status"] = body.status
        if body.surface is not None:
            update_data["surface"] = body.surface
        if body.material is not None:
            update_data["material"] = body.material
        if body.notes is not None:
            update_data["notes"] = body.notes

        for key, value in update_data.items():
            setattr(row, key, value)
        row.updated_at = datetime.now(UTC)

        await session.commit()
        await session.refresh(row)

    logger.info(
        "Tooth condition updated: patient_id=%s condition_id=%s",
        patient_id,
        condition_id,
    )

    return _row_to_schema(row)


@router.delete("/conditions/{condition_id}", status_code=204)
async def delete_tooth_condition(
    patient_id: uuid.UUID,
    condition_id: uuid.UUID,
    request: Request,
) -> None:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(ToothConditionModel)
            .where(
                ToothConditionModel.id == condition_id,
                ToothConditionModel.patient_id == patient_id,
                ToothConditionModel.practice_id == practice_id,
                ToothConditionModel.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="CONDITION_NOT_FOUND", message="Tooth condition not found")
                ).model_dump(by_alias=True),
            )

        row.deleted_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        await session.commit()

    logger.info(
        "Tooth condition deleted: patient_id=%s condition_id=%s",
        patient_id,
        condition_id,
    )
