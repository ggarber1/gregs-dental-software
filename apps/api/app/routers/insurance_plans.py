from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.core.db import get_session_factory
from app.models.insurance_plan import InsurancePlan as InsurancePlanModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import (
    ApiError,
    CreateInsurancePlan,
    Error,
    InsurancePlan,
    UpdateInsurancePlan,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/insurance-plans", tags=["insurance-plans"])


def _row_to_schema(row: InsurancePlanModel) -> InsurancePlan:
    return InsurancePlan(
        id=row.id,
        practiceId=row.practice_id,
        carrierName=row.carrier_name,
        payerId=row.payer_id,
        groupNumber=row.group_number,
        isInNetwork=row.is_in_network,
        createdAt=row.created_at.replace(tzinfo=UTC),
        updatedAt=row.updated_at.replace(tzinfo=UTC),
    )


@router.get("", response_model=list[InsurancePlan])
async def list_insurance_plans(request: Request) -> list[InsurancePlan]:
    practice_id = _require_practice_scope(request)

    async with get_session_factory()() as session:
        rows = (
            await session.scalars(
                select(InsurancePlanModel)
                .where(
                    InsurancePlanModel.practice_id == practice_id,
                    InsurancePlanModel.deleted_at.is_(None),
                )
                .order_by(InsurancePlanModel.carrier_name.asc())
            )
        ).all()

    return [_row_to_schema(r) for r in rows]


@router.post("", status_code=201, response_model=InsurancePlan)
async def create_insurance_plan(body: CreateInsurancePlan, request: Request) -> InsurancePlan:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    row = InsurancePlanModel(
        id=uuid.uuid4(),
        practice_id=practice_id,
        carrier_name=body.carrier_name,
        payer_id=body.payer_id,
        group_number=body.group_number,
        is_in_network=body.is_in_network if body.is_in_network is not None else True,
    )

    async with get_session_factory()() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)

    logger.info(
        "insurance_plan.created",
        extra={"plan_id": str(row.id), "practice_id": str(practice_id)},
    )
    return _row_to_schema(row)


@router.patch("/{plan_id}", response_model=InsurancePlan)
async def patch_insurance_plan(
    plan_id: uuid.UUID,
    body: UpdateInsurancePlan,
    request: Request,
) -> InsurancePlan:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(InsurancePlanModel).where(
                InsurancePlanModel.id == plan_id,
                InsurancePlanModel.practice_id == practice_id,
                InsurancePlanModel.deleted_at.is_(None),
            )
        )
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="INSURANCE_PLAN_NOT_FOUND", message="Insurance plan not found")
                ).model_dump(by_alias=True),
            )

        provided = body.model_fields_set
        if "carrier_name" in provided and body.carrier_name is not None:
            row.carrier_name = body.carrier_name
        if "payer_id" in provided and body.payer_id is not None:
            row.payer_id = body.payer_id
        if "group_number" in provided:
            row.group_number = body.group_number
        if "is_in_network" in provided and body.is_in_network is not None:
            row.is_in_network = body.is_in_network

        row.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(row)

    return _row_to_schema(row)


@router.delete("/{plan_id}", status_code=204)
async def delete_insurance_plan(plan_id: uuid.UUID, request: Request) -> None:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(InsurancePlanModel).where(
                InsurancePlanModel.id == plan_id,
                InsurancePlanModel.practice_id == practice_id,
                InsurancePlanModel.deleted_at.is_(None),
            )
        )
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="INSURANCE_PLAN_NOT_FOUND", message="Insurance plan not found")
                ).model_dump(by_alias=True),
            )

        row.deleted_at = datetime.now(UTC)
        await session.commit()

    logger.info(
        "insurance_plan.deleted",
        extra={"plan_id": str(plan_id), "practice_id": str(practice_id)},
    )
