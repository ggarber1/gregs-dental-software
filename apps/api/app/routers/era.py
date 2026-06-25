from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.core.db import get_session_factory
from app.core.features import feature_enabled, require_feature
from app.core.ssm import get_ssm_parameter
from app.models.era_remittance import ERARemittance as ERARemittanceModel
from app.models.era_remittance import UnmatchedERAPayment as UnmatchedModel
from app.models.practice import Practice as PracticeModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import (
    ApiError,
    ERAPollSummary,
    ERARemittance,
    Error,
    UnmatchedERAPayment,
)
from app.services.era.service import poll_and_post_eras, resolve_unmatched_payment
from app.services.era.stedi import StediRemittanceClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["era"])

_FEATURE = "claims_submission"
_POLL_WINDOW_DAYS = 30


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=ApiError(error=Error(code=code, message=message)).model_dump(by_alias=True),
    )


def _remittance_schema(row: ERARemittanceModel) -> ERARemittance:
    return ERARemittance(
        id=row.id,
        practiceId=row.practice_id,
        stediTransactionId=row.stedi_transaction_id,
        payerName=row.payer_name,
        traceNumber=row.trace_number,
        paymentCents=row.payment_cents,
        paymentDate=row.payment_date.isoformat() if row.payment_date else None,
        claimCount=row.claim_count,
        matchedCount=row.matched_count,
        unmatchedCount=row.unmatched_count,
        createdAt=row.created_at.replace(tzinfo=UTC),
    )


def _unmatched_schema(row: UnmatchedModel) -> UnmatchedERAPayment:
    return UnmatchedERAPayment(
        id=row.id,
        practiceId=row.practice_id,
        remittanceId=row.remittance_id,
        patientControlNumber=row.patient_control_number,
        payerClaimControlNumber=row.payer_claim_control_number,
        paidCents=row.paid_cents,
        resolved=row.resolved,
        resolvedAt=row.resolved_at.replace(tzinfo=UTC) if row.resolved_at else None,
        createdAt=row.created_at.replace(tzinfo=UTC),
    )


@router.post("/era/poll", response_model=ERAPollSummary)
async def poll_eras(request: Request) -> ERAPollSummary:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_sub = getattr(request.state.user, "sub", None)

    async with get_session_factory()() as session:
        practice = await session.scalar(
            select(PracticeModel).where(PracticeModel.id == practice_id)
        )
        await require_feature(session, practice_id, _FEATURE, practice=practice)
        assert practice is not None  # require_feature 403s when the practice is missing

        if not practice.clearinghouse_api_key_ssm_path:
            raise _err(422, "MISSING_CLEARINGHOUSE", "Clearinghouse credentials are not configured")
        api_key = get_ssm_parameter(practice.clearinghouse_api_key_ssm_path)
        if not api_key:
            raise _err(422, "MISSING_CLEARINGHOUSE", "Clearinghouse API key unavailable")

        client = StediRemittanceClient(api_key=api_key)
        since = datetime.now(UTC) - timedelta(days=_POLL_WINDOW_DAYS)
        summary = await poll_and_post_eras(
            session,
            practice_id,
            client=client,
            since=since,
            user_sub=user_sub,
            post_to_ledger=feature_enabled(practice, "billing_ledger"),
        )
        return ERAPollSummary(
            polled=summary["polled"],
            new=summary["new"],
            matched=summary["matched"],
            unmatched=summary["unmatched"],
            remittanceIds=summary["remittance_ids"],
        )


@router.get("/era/remittances", response_model=list[ERARemittance])
async def list_remittances(request: Request) -> list[ERARemittance]:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        rows = (
            await session.scalars(
                select(ERARemittanceModel)
                .where(
                    ERARemittanceModel.practice_id == practice_id,
                    ERARemittanceModel.deleted_at.is_(None),
                )
                .order_by(ERARemittanceModel.created_at.desc())
            )
        ).all()
        return [_remittance_schema(r) for r in rows]


@router.get("/era/unmatched", response_model=list[UnmatchedERAPayment])
async def list_unmatched(request: Request, resolved: bool = False) -> list[UnmatchedERAPayment]:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        rows = (
            await session.scalars(
                select(UnmatchedModel)
                .where(
                    UnmatchedModel.practice_id == practice_id,
                    UnmatchedModel.resolved == resolved,
                    UnmatchedModel.deleted_at.is_(None),
                )
                .order_by(UnmatchedModel.created_at.desc())
            )
        ).all()
        return [_unmatched_schema(r) for r in rows]


@router.post("/era/unmatched/{unmatched_id}/resolve", response_model=UnmatchedERAPayment)
async def resolve_unmatched(unmatched_id: uuid.UUID, request: Request) -> UnmatchedERAPayment:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        row = await resolve_unmatched_payment(session, practice_id, unmatched_id)
        if row is None:
            raise _err(404, "UNMATCHED_NOT_FOUND", "Unmatched payment not found")
        return _unmatched_schema(row)
