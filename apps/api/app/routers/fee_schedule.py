from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.models.appointment_procedure import CdtCode as CdtCodeModel
from app.models.fee_schedule import PracticeFeeSchedule as FeeScheduleModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import ApiError, Error, FeeScheduleRow, SetFee

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/fee-schedule", tags=["fee-schedule"])


def _err(code: str, message: str) -> dict[str, Any]:
    return ApiError(error=Error(code=code, message=message)).model_dump(by_alias=True)


def _row_to_schema(cdt: CdtCodeModel, practice_fee_cents: int | None) -> FeeScheduleRow:
    resolved = practice_fee_cents if practice_fee_cents is not None else cdt.default_fee_cents
    return FeeScheduleRow(
        cdtCodeId=cdt.id,
        code=cdt.code,
        description=cdt.description,
        category=cdt.category,  # type: ignore[arg-type]
        defaultFeeCents=cdt.default_fee_cents,  # type: ignore[arg-type]
        practiceFeeCents=practice_fee_cents,  # type: ignore[arg-type]
        resolvedFeeCents=resolved,  # type: ignore[arg-type]
    )


@router.get("", response_model=list[FeeScheduleRow])
async def list_fee_schedule(request: Request) -> list[FeeScheduleRow]:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        result = await session.execute(
            select(CdtCodeModel, FeeScheduleModel.fee_cents)
            .outerjoin(
                FeeScheduleModel,
                and_(
                    FeeScheduleModel.cdt_code_id == CdtCodeModel.id,
                    FeeScheduleModel.practice_id == practice_id,
                    FeeScheduleModel.deleted_at.is_(None),
                ),
            )
            .where(
                CdtCodeModel.is_active.is_(True),
                CdtCodeModel.deleted_at.is_(None),
            )
            .order_by(CdtCodeModel.code.asc())
        )
        return [_row_to_schema(cdt, fee) for cdt, fee in result.all()]


async def _load_active_code(session: AsyncSession, code: str) -> CdtCodeModel:
    cdt: CdtCodeModel | None = await session.scalar(
        select(CdtCodeModel).where(
            CdtCodeModel.code == code,
            CdtCodeModel.is_active.is_(True),
            CdtCodeModel.deleted_at.is_(None),
        )
    )
    if cdt is None:
        raise HTTPException(status_code=404, detail=_err("CDT_CODE_NOT_FOUND", "Unknown CDT code"))
    return cdt


@router.put("/{code}", response_model=FeeScheduleRow)
async def set_fee(code: str, body: SetFee, request: Request) -> FeeScheduleRow:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    async with get_session_factory()() as session:
        cdt = await _load_active_code(session, code)
        row = await session.scalar(
            select(FeeScheduleModel).where(
                FeeScheduleModel.practice_id == practice_id,
                FeeScheduleModel.cdt_code_id == cdt.id,
                FeeScheduleModel.deleted_at.is_(None),
            )
        )
        if row is None:
            row = FeeScheduleModel(
                id=uuid.uuid4(),
                practice_id=practice_id,
                cdt_code_id=cdt.id,
                fee_cents=body.fee_cents,
            )
            session.add(row)
        else:
            row.fee_cents = body.fee_cents
            row.updated_at = datetime.now(UTC)
        await session.commit()
        schema = _row_to_schema(cdt, body.fee_cents)
    logger.info("fee_schedule.set", extra={"practice_id": str(practice_id), "code": code})
    return schema


@router.delete("/{code}", status_code=204)
async def revert_fee(code: str, request: Request) -> None:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    async with get_session_factory()() as session:
        cdt = await _load_active_code(session, code)
        row = await session.scalar(
            select(FeeScheduleModel).where(
                FeeScheduleModel.practice_id == practice_id,
                FeeScheduleModel.cdt_code_id == cdt.id,
                FeeScheduleModel.deleted_at.is_(None),
            )
        )
        if row is not None:
            row.deleted_at = datetime.now(UTC)
            await session.commit()
    logger.info("fee_schedule.reverted", extra={"practice_id": str(practice_id), "code": code})
