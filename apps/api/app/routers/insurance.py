from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.core.db import get_session_factory
from app.models.insurance_plan import InsurancePlan as InsurancePlanModel
from app.models.patient_insurance import PatientInsurance as InsuranceModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import (
    ApiError,
    CreateInsurance,
    Error,
    Insurance,
    UpdateInsurance,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/patients/{patient_id}/insurance", tags=["insurance"])


def _row_to_schema(row: InsuranceModel) -> Insurance:
    return Insurance(
        id=row.id,
        patientId=row.patient_id,
        practiceId=row.practice_id,
        insurancePlanId=row.insurance_plan_id,
        priority=row.priority,  # type: ignore[arg-type]
        carrier=row.carrier,
        memberId=row.member_id,
        groupNumber=row.group_number,
        relationshipToInsured=row.relationship_to_insured,  # type: ignore[arg-type]
        insuredFirstName=row.insured_first_name,
        insuredLastName=row.insured_last_name,
        insuredDateOfBirth=row.insured_date_of_birth,
        isActive=row.is_active,
        createdAt=row.created_at.replace(tzinfo=UTC),
        updatedAt=row.updated_at.replace(tzinfo=UTC),
    )


async def _resolve_plan_carrier(
    session: object,
    insurance_plan_id: uuid.UUID,
    practice_id: uuid.UUID,
) -> str:
    plan = await session.scalar(  # type: ignore[union-attr]
        select(InsurancePlanModel).where(
            InsurancePlanModel.id == insurance_plan_id,
            InsurancePlanModel.practice_id == practice_id,
            InsurancePlanModel.deleted_at.is_(None),
        )
    )
    if plan is None:
        raise HTTPException(
            status_code=404,
            detail=ApiError(
                error=Error(
                    code="INSURANCE_PLAN_NOT_FOUND",
                    message="Insurance plan not found or does not belong to this practice",
                )
            ).model_dump(by_alias=True),
        )
    return plan.carrier_name


@router.get("", response_model=list[Insurance])
async def list_patient_insurance(patient_id: uuid.UUID, request: Request) -> list[Insurance]:
    practice_id = _require_practice_scope(request)

    async with get_session_factory()() as session:
        rows = (
            await session.scalars(
                select(InsuranceModel)
                .where(
                    InsuranceModel.patient_id == patient_id,
                    InsuranceModel.practice_id == practice_id,
                    InsuranceModel.deleted_at.is_(None),
                )
                .order_by(InsuranceModel.priority.asc(), InsuranceModel.created_at.asc())
            )
        ).all()

    return [_row_to_schema(r) for r in rows]


@router.post("", status_code=201, response_model=Insurance)
async def create_patient_insurance(
    patient_id: uuid.UUID,
    body: CreateInsurance,
    request: Request,
) -> Insurance:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        carrier = body.carrier
        if body.insurance_plan_id is not None:
            carrier = await _resolve_plan_carrier(session, body.insurance_plan_id, practice_id)

        row = InsuranceModel(
            id=uuid.uuid4(),
            patient_id=patient_id,
            practice_id=practice_id,
            insurance_plan_id=body.insurance_plan_id,
            priority=body.priority or "primary",
            carrier=carrier,
            member_id=body.member_id,
            group_number=body.group_number,
            relationship_to_insured=body.relationship_to_insured or "self",
            insured_first_name=body.insured_first_name,
            insured_last_name=body.insured_last_name,
            insured_date_of_birth=body.insured_date_of_birth,
            is_active=True,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)

    return _row_to_schema(row)


@router.patch("/{insurance_id}", response_model=Insurance)
async def patch_patient_insurance(
    patient_id: uuid.UUID,
    insurance_id: uuid.UUID,
    body: UpdateInsurance,
    request: Request,
) -> Insurance:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(InsuranceModel).where(
                InsuranceModel.id == insurance_id,
                InsuranceModel.patient_id == patient_id,
                InsuranceModel.practice_id == practice_id,
                InsuranceModel.deleted_at.is_(None),
            )
        )
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="INSURANCE_NOT_FOUND", message="Insurance record not found")
                ).model_dump(by_alias=True),
            )

        provided = body.model_fields_set

        if "insurance_plan_id" in provided and body.insurance_plan_id is not None:
            carrier_name = await _resolve_plan_carrier(session, body.insurance_plan_id, practice_id)
            row.insurance_plan_id = body.insurance_plan_id
            row.carrier = carrier_name
        elif "carrier" in provided and body.carrier is not None:
            row.carrier = body.carrier

        if "priority" in provided and body.priority is not None:
            row.priority = body.priority
        if "member_id" in provided:
            row.member_id = body.member_id
        if "group_number" in provided:
            row.group_number = body.group_number
        if "relationship_to_insured" in provided and body.relationship_to_insured is not None:
            row.relationship_to_insured = body.relationship_to_insured
        if "insured_first_name" in provided:
            row.insured_first_name = body.insured_first_name
        if "insured_last_name" in provided:
            row.insured_last_name = body.insured_last_name
        if "insured_date_of_birth" in provided:
            row.insured_date_of_birth = body.insured_date_of_birth

        row.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(row)

    return _row_to_schema(row)


@router.delete("/{insurance_id}", status_code=204)
async def delete_patient_insurance(
    patient_id: uuid.UUID,
    insurance_id: uuid.UUID,
    request: Request,
) -> None:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(InsuranceModel).where(
                InsuranceModel.id == insurance_id,
                InsuranceModel.patient_id == patient_id,
                InsuranceModel.practice_id == practice_id,
                InsuranceModel.deleted_at.is_(None),
            )
        )
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="INSURANCE_NOT_FOUND", message="Insurance record not found")
                ).model_dump(by_alias=True),
            )

        row.deleted_at = datetime.now(UTC)
        await session.commit()
