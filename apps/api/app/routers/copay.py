from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.core.features import require_feature
from app.models.copay_calculation import CopayCalculation as CalcModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import ApiError, CopayEstimate, Error, OverrideCopay
from app.services.copay.service import CopayCalculationError, calculate_for_appointment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/appointments/{appointment_id}", tags=["copay"])

_FEATURE = "copay_estimation"
_REQUIRES = "eligibility_verification"


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=ApiError(error=Error(code=code, message=message)).model_dump(by_alias=True),
    )


def _to_schema(row: CalcModel) -> CopayEstimate:
    return CopayEstimate(
        id=row.id,
        appointmentId=row.appointment_id,
        eligibilityCheckId=row.eligibility_check_id,
        calculatedAt=row.calculated_at.replace(tzinfo=UTC),
        planType=row.plan_type,  # type: ignore[arg-type]
        totalProviderFeeCents=row.total_provider_fee_cents,
        totalWriteOffCents=row.total_write_off_cents,
        totalInsuranceOwesCents=row.total_insurance_owes_cents,
        totalPatientOwesCents=row.total_patient_owes_cents,
        deductibleRemainingAfterCents=row.deductible_remaining_after_cents,
        annualMaxRemainingAfterCents=row.annual_max_remaining_after_cents,
        overridePatientCents=row.override_patient_cents,
        overrideNote=row.override_note,
        hasSecondaryInsurance=row.has_secondary_insurance,
        lineItems=row.line_items,  # type: ignore[arg-type]
    )


async def _gate(session: AsyncSession, practice_id: uuid.UUID) -> None:
    await require_feature(session, practice_id, _FEATURE)
    await require_feature(session, practice_id, _REQUIRES)


@router.post("/copay-estimate", status_code=201, response_model=CopayEstimate)
async def create_copay_estimate(appointment_id: uuid.UUID, request: Request) -> CopayEstimate:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_sub = getattr(request.state.user, "sub", None)
    async with get_session_factory()() as session:
        await _gate(session, practice_id)
        try:
            calc = await calculate_for_appointment(session, practice_id, appointment_id, user_sub)
        except CopayCalculationError as exc:
            status = 404 if exc.code == "APPOINTMENT_NOT_FOUND" else 422
            raise _err(status, exc.code, exc.message) from exc
        return _to_schema(calc)


async def _latest(
    session: AsyncSession, practice_id: uuid.UUID, appointment_id: uuid.UUID
) -> CalcModel:
    row: CalcModel | None = await session.scalar(
        select(CalcModel)
        .where(
            CalcModel.appointment_id == appointment_id,
            CalcModel.practice_id == practice_id,
            CalcModel.deleted_at.is_(None),
        )
        .order_by(CalcModel.calculated_at.desc())
    )
    if row is None:
        raise _err(404, "COPAY_ESTIMATE_NOT_FOUND", "No estimate for this appointment")
    return row


@router.get("/copay-estimate", response_model=CopayEstimate)
async def get_copay_estimate(appointment_id: uuid.UUID, request: Request) -> CopayEstimate:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await _gate(session, practice_id)
        return _to_schema(await _latest(session, practice_id, appointment_id))


@router.patch("/copay-estimate", response_model=CopayEstimate)
async def override_copay_estimate(
    appointment_id: uuid.UUID, body: OverrideCopay, request: Request
) -> CopayEstimate:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_sub = getattr(request.state.user, "sub", None)
    async with get_session_factory()() as session:
        await _gate(session, practice_id)
        row = await _latest(session, practice_id, appointment_id)
        row.override_patient_cents = (
            body.override_patient_cents.root
            if body.override_patient_cents is not None
            else None
        )
        row.override_note = body.override_note
        row.overridden_by = user_sub
        row.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(row)
        return _to_schema(row)
