from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.core.features import require_feature
from app.models.appointment_procedure import CdtCode as CdtCodeModel
from app.models.contracted_fee_schedule import ContractedFeeSchedule as ContractedModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import (
    AllowedAmountCents,
    ApiError,
    ContractedFeeRow,
    Error,
    SetContractedFee,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/contracted-fees", tags=["contracted-fees"])

_FEATURE = "copay_estimation"


def _cents(v: AllowedAmountCents | None) -> int | None:
    """Unwrap AllowedAmountCents RootModel to a plain int (or None)."""
    return v.root if v is not None else None


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=ApiError(error=Error(code=code, message=message)).model_dump(by_alias=True),
    )


def _row_to_schema(
    cdt: CdtCodeModel, payer_id: str, row: ContractedModel | None
) -> ContractedFeeRow:
    return ContractedFeeRow(
        cdtCodeId=cdt.id,
        code=cdt.code,
        description=cdt.description,
        category=cdt.category,  # type: ignore[arg-type]
        payerId=payer_id,
        allowedAmountCents=row.allowed_amount_cents if row else None,  # type: ignore[arg-type]
        notCovered=row.not_covered if row else False,
        requiresPriorAuth=row.requires_prior_auth if row else False,
    )


@router.get("", response_model=list[ContractedFeeRow])
async def list_contracted_fees(payer_id: str, request: Request) -> list[ContractedFeeRow]:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        result = await session.execute(
            select(CdtCodeModel, ContractedModel)
            .outerjoin(
                ContractedModel,
                and_(
                    ContractedModel.cdt_code_id == CdtCodeModel.id,
                    ContractedModel.practice_id == practice_id,
                    ContractedModel.payer_id == payer_id,
                    ContractedModel.deleted_at.is_(None),
                ),
            )
            .where(CdtCodeModel.is_active.is_(True), CdtCodeModel.deleted_at.is_(None))
            .order_by(CdtCodeModel.code.asc())
        )
        return [_row_to_schema(cdt, payer_id, row) for cdt, row in result.all()]


async def _load_active_code(session: AsyncSession, cdt_code_id: uuid.UUID) -> CdtCodeModel:
    cdt = await session.scalar(
        select(CdtCodeModel).where(
            CdtCodeModel.id == cdt_code_id,
            CdtCodeModel.is_active.is_(True),
            CdtCodeModel.deleted_at.is_(None),
        )
    )
    if cdt is None:
        raise _err(404, "CDT_CODE_NOT_FOUND", "Unknown CDT code")
    return cdt


@router.put("/{cdt_code_id}", response_model=ContractedFeeRow)
async def set_contracted_fee(
    cdt_code_id: uuid.UUID, payer_id: str, body: SetContractedFee, request: Request
) -> ContractedFeeRow:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        cdt = await _load_active_code(session, cdt_code_id)
        row = await session.scalar(
            select(ContractedModel).where(
                ContractedModel.practice_id == practice_id,
                ContractedModel.payer_id == payer_id,
                ContractedModel.cdt_code_id == cdt.id,
                ContractedModel.deleted_at.is_(None),
            )
        )
        if row is None:
            row = ContractedModel(
                id=uuid.uuid4(),
                practice_id=practice_id,
                payer_id=payer_id,
                cdt_code_id=cdt.id,
                allowed_amount_cents=_cents(body.allowed_amount_cents),
                not_covered=body.not_covered if body.not_covered is not None else False,
                requires_prior_auth=(
                    body.requires_prior_auth if body.requires_prior_auth is not None else False
                ),
            )
            session.add(row)
        else:
            row.allowed_amount_cents = _cents(body.allowed_amount_cents)
            if body.not_covered is not None:
                row.not_covered = body.not_covered
            if body.requires_prior_auth is not None:
                row.requires_prior_auth = body.requires_prior_auth
            row.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(row)
        return _row_to_schema(cdt, payer_id, row)


@router.delete("/{cdt_code_id}", status_code=204)
async def revert_contracted_fee(
    cdt_code_id: uuid.UUID, payer_id: str, request: Request
) -> None:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        row = await session.scalar(
            select(ContractedModel).where(
                ContractedModel.practice_id == practice_id,
                ContractedModel.payer_id == payer_id,
                ContractedModel.cdt_code_id == cdt_code_id,
                ContractedModel.deleted_at.is_(None),
            )
        )
        if row is not None:
            row.deleted_at = datetime.now(UTC)
            await session.commit()
    logger.info(
        "contracted_fee.reverted",
        extra={
            "practice_id": str(practice_id),
            "payer_id": payer_id,
            "cdt_code_id": str(cdt_code_id),
        },
    )
