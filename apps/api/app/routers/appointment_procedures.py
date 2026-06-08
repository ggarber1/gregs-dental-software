from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.models.appointment import Appointment as AppointmentModel
from app.models.appointment_procedure import AppointmentProcedure as ProcedureModel
from app.models.appointment_procedure import CdtCode as CdtCodeModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import (
    ApiError,
    AppointmentProcedure,
    AppointmentProcedureListResponse,
    CdtCode,
    CreateAppointmentProcedure,
    Error,
    ProcedureTotals,
    UpdateAppointmentProcedure,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/appointments/{appointment_id}/procedures",
    tags=["appointment-procedures"],
)
cdt_router = APIRouter(prefix="/api/v1/cdt-codes", tags=["appointment-procedures"])
patient_router = APIRouter(
    prefix="/api/v1/patients/{patient_id}/procedures",
    tags=["appointment-procedures"],
)

_CDT_SEARCH_LIMIT = 25


def _err(code: str, message: str) -> dict[str, Any]:
    return ApiError(error=Error(code=code, message=message)).model_dump(by_alias=True)


def _cdt_to_schema(row: CdtCodeModel) -> CdtCode:
    return CdtCode(
        id=row.id,
        code=row.code,
        description=row.description,
        category=row.category,  # type: ignore[arg-type]
        defaultFeeCents=row.default_fee_cents,  # type: ignore[arg-type]
        isActive=row.is_active,
    )


def _proc_to_schema(row: ProcedureModel) -> AppointmentProcedure:
    return AppointmentProcedure(
        id=row.id,
        practiceId=row.practice_id,
        appointmentId=row.appointment_id,
        patientId=row.patient_id,
        cdtCodeId=row.cdt_code_id,
        procedureCode=row.procedure_code,
        procedureName=row.procedure_name,
        toothNumber=row.tooth_number,
        surface=row.surface,
        feeCents=row.fee_cents,
        insuranceEstCents=row.insurance_est_cents,  # type: ignore[arg-type]
        patientEstCents=row.patient_est_cents,  # type: ignore[arg-type]
        estimateSource=row.estimate_source,  # type: ignore[arg-type]
        notes=row.notes,
        createdAt=row.created_at.replace(tzinfo=UTC),
        updatedAt=row.updated_at.replace(tzinfo=UTC),
    )


def _totals(rows: list[ProcedureModel]) -> ProcedureTotals:
    return ProcedureTotals(
        feeCentsTotal=sum(r.fee_cents for r in rows),
        insuranceEstCentsTotal=sum(r.insurance_est_cents or 0 for r in rows),
        patientEstCentsTotal=sum(r.patient_est_cents or 0 for r in rows),
    )


async def _load_scoped_appointment(
    session: AsyncSession, appointment_id: uuid.UUID, practice_id: uuid.UUID
) -> AppointmentModel:
    appt = await session.scalar(
        select(AppointmentModel).where(
            AppointmentModel.id == appointment_id,
            AppointmentModel.practice_id == practice_id,
            AppointmentModel.deleted_at.is_(None),
        )
    )
    if appt is None:
        raise HTTPException(
            status_code=404,
            detail=_err("APPOINTMENT_NOT_FOUND", "Appointment not found"),
        )
    return appt


async def _load_scoped_procedure(
    session: AsyncSession,
    appointment_id: uuid.UUID,
    procedure_id: uuid.UUID,
    practice_id: uuid.UUID,
) -> ProcedureModel:
    row = await session.scalar(
        select(ProcedureModel).where(
            ProcedureModel.id == procedure_id,
            ProcedureModel.appointment_id == appointment_id,
            ProcedureModel.practice_id == practice_id,
            ProcedureModel.deleted_at.is_(None),
        )
    )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=_err("PROCEDURE_NOT_FOUND", "Procedure not found"),
        )
    return row


def _resolve_code_fields(body: CreateAppointmentProcedure) -> str | None:
    if body.cdt_code_id is None and not body.procedure_code:
        raise HTTPException(
            status_code=422,
            detail=_err(
                "PROCEDURE_CODE_REQUIRED",
                "Either cdtCodeId or procedureCode must be provided",
            ),
        )
    return body.procedure_code


@cdt_router.get("", response_model=list[CdtCode])
async def search_cdt_codes(request: Request, q: str | None = None) -> list[CdtCode]:
    _require_practice_scope(request)
    async with get_session_factory()() as session:
        query = select(CdtCodeModel).where(
            CdtCodeModel.is_active.is_(True), CdtCodeModel.deleted_at.is_(None)
        )
        if q:
            term = q.strip()
            query = query.where(
                or_(
                    CdtCodeModel.code.ilike(f"{term}%"),
                    CdtCodeModel.description.ilike(f"%{term}%"),
                )
            )
        query = query.order_by(CdtCodeModel.code.asc()).limit(_CDT_SEARCH_LIMIT)
        rows = (await session.scalars(query)).all()
    return [_cdt_to_schema(r) for r in rows]


@router.get("", response_model=AppointmentProcedureListResponse)
async def list_procedures(
    appointment_id: uuid.UUID, request: Request
) -> AppointmentProcedureListResponse:
    practice_id = _require_practice_scope(request)
    user_sub = getattr(request.state.user, "sub", None)
    async with get_session_factory()() as session:
        await _load_scoped_appointment(session, appointment_id, practice_id)
        rows = (
            await session.scalars(
                select(ProcedureModel)
                .where(
                    ProcedureModel.appointment_id == appointment_id,
                    ProcedureModel.deleted_at.is_(None),
                )
                .order_by(ProcedureModel.created_at.asc())
            )
        ).all()
        if rows:
            await session.execute(
                update(ProcedureModel)
                .where(ProcedureModel.id.in_([r.id for r in rows]))
                .values(last_accessed_by=user_sub, last_accessed_at=datetime.now(UTC))
                .execution_options(synchronize_session=False)
            )
            await session.commit()
    return AppointmentProcedureListResponse(
        items=[_proc_to_schema(r).model_dump(by_alias=True) for r in rows],  # type: ignore[misc]
        totals=_totals(list(rows)).model_dump(by_alias=True),  # type: ignore[arg-type]
    )


@patient_router.get("", response_model=AppointmentProcedureListResponse)
async def list_patient_procedures(
    patient_id: uuid.UUID, request: Request
) -> AppointmentProcedureListResponse:
    practice_id = _require_practice_scope(request)
    user_sub = getattr(request.state.user, "sub", None)
    async with get_session_factory()() as session:
        rows = (
            await session.scalars(
                select(ProcedureModel)
                .where(
                    ProcedureModel.patient_id == patient_id,
                    ProcedureModel.practice_id == practice_id,
                    ProcedureModel.deleted_at.is_(None),
                )
                .order_by(ProcedureModel.created_at.desc())
            )
        ).all()
        if rows:
            await session.execute(
                update(ProcedureModel)
                .where(ProcedureModel.id.in_([r.id for r in rows]))
                .values(last_accessed_by=user_sub, last_accessed_at=datetime.now(UTC))
                .execution_options(synchronize_session=False)
            )
            await session.commit()
    return AppointmentProcedureListResponse(
        items=[_proc_to_schema(r).model_dump(by_alias=True) for r in rows],  # type: ignore[misc]
        totals=_totals(list(rows)).model_dump(by_alias=True),  # type: ignore[arg-type]
    )


@router.post("", status_code=201, response_model=AppointmentProcedure)
async def create_procedure(
    appointment_id: uuid.UUID, body: CreateAppointmentProcedure, request: Request
) -> AppointmentProcedure:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_sub = getattr(request.state.user, "sub", None)
    procedure_code = _resolve_code_fields(body)
    async with get_session_factory()() as session:
        appt = await _load_scoped_appointment(session, appointment_id, practice_id)
        if appt.patient_id is None:
            raise HTTPException(
                status_code=422,
                detail=_err(
                    "APPOINTMENT_HAS_NO_PATIENT",
                    "Cannot add procedures to an appointment without a patient",
                ),
            )
        if body.cdt_code_id is not None:
            cdt = await session.scalar(
                select(CdtCodeModel).where(
                    CdtCodeModel.id == body.cdt_code_id,
                    CdtCodeModel.deleted_at.is_(None),
                )
            )
            if cdt is None:
                raise HTTPException(
                    status_code=422,
                    detail=_err("CDT_CODE_NOT_FOUND", "Unknown CDT code"),
                )
            if not procedure_code:
                procedure_code = cdt.code
        row = ProcedureModel(
            id=uuid.uuid4(),
            practice_id=practice_id,
            appointment_id=appointment_id,
            patient_id=appt.patient_id,
            cdt_code_id=body.cdt_code_id,
            procedure_code=procedure_code,
            procedure_name=body.procedure_name,
            tooth_number=body.tooth_number,
            surface=body.surface,
            fee_cents=body.fee_cents,
            insurance_est_cents=body.insurance_est_cents,
            patient_est_cents=body.patient_est_cents,
            estimate_source=body.estimate_source,
            notes=body.notes,
            last_accessed_by=user_sub,
            last_accessed_at=datetime.now(UTC),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
    logger.info(
        "Procedure added: appointment_id=%s procedure_id=%s", appointment_id, row.id
    )
    return _proc_to_schema(row)


@router.patch("/{procedure_id}", response_model=AppointmentProcedure)
async def update_procedure(
    appointment_id: uuid.UUID,
    procedure_id: uuid.UUID,
    body: UpdateAppointmentProcedure,
    request: Request,
) -> AppointmentProcedure:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_sub = getattr(request.state.user, "sub", None)
    async with get_session_factory()() as session:
        await _load_scoped_appointment(session, appointment_id, practice_id)
        row = await _load_scoped_procedure(
            session, appointment_id, procedure_id, practice_id
        )
        data = body.model_dump(by_alias=False, exclude_unset=True)
        for attr in (
            "cdt_code_id",
            "procedure_code",
            "procedure_name",
            "tooth_number",
            "surface",
            "fee_cents",
            "insurance_est_cents",
            "patient_est_cents",
            "estimate_source",
            "notes",
        ):
            if attr in data:
                setattr(row, attr, data[attr])
        if row.cdt_code_id is None and not row.procedure_code:
            raise HTTPException(
                status_code=422,
                detail=_err(
                    "PROCEDURE_CODE_REQUIRED",
                    "Either cdtCodeId or procedureCode must be present",
                ),
            )
        row.last_accessed_by = user_sub
        row.last_accessed_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(row)
    return _proc_to_schema(row)


@router.delete("/{procedure_id}", status_code=204)
async def delete_procedure(
    appointment_id: uuid.UUID, procedure_id: uuid.UUID, request: Request
) -> None:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    async with get_session_factory()() as session:
        await _load_scoped_appointment(session, appointment_id, practice_id)
        row = await _load_scoped_procedure(
            session, appointment_id, procedure_id, practice_id
        )
        row.deleted_at = datetime.now(UTC)
        await session.commit()
