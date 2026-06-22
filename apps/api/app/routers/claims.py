from __future__ import annotations

import logging
import uuid
from datetime import UTC

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.features import require_feature
from app.core.ssm import get_ssm_parameter
from app.models.claim import Claim as ClaimModel
from app.models.practice import Practice as PracticeModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import ApiError, Claim, ClaimStatus, Error
from app.services.claims.service import (
    ClaimSubmissionPrereqError,
    submit_claim_for_appointment,
)
from app.services.claims.stedi import StediClaimsClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["claims"])

_FEATURE = "claims_submission"


def _usage_indicator() -> str:
    # 'T' for any non-production environment; 'P' only in production.
    return "P" if get_settings().is_production else "T"


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=ApiError(error=Error(code=code, message=message)).model_dump(by_alias=True),
    )


def _to_schema(row: ClaimModel) -> Claim:
    return Claim(
        id=row.id,
        practiceId=row.practice_id,
        appointmentId=row.appointment_id,
        patientId=row.patient_id,
        insuranceId=row.insurance_id,
        providerId=row.provider_id,
        idempotencyKey=row.idempotency_key,
        submissionAttempt=row.submission_attempt,
        patientControlNumber=row.patient_control_number,
        payerId=row.payer_id,
        status=row.status,  # type: ignore[arg-type]
        totalChargeCents=row.total_charge_cents,
        clearinghouseClaimId=row.clearinghouse_claim_id,
        clearinghouseStatus=row.clearinghouse_status,
        submissionErrors=row.submission_errors,
        submittedAt=row.submitted_at.replace(tzinfo=UTC) if row.submitted_at else None,
        createdAt=(row.created_at).replace(tzinfo=UTC),
        updatedAt=(row.updated_at).replace(tzinfo=UTC),
    )


@router.post("/appointments/{appointment_id}/claim", status_code=201, response_model=Claim)
async def submit_claim(appointment_id: uuid.UUID, request: Request) -> Claim:
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

        client = StediClaimsClient(api_key=api_key)
        try:
            claim = await submit_claim_for_appointment(
                session,
                practice_id,
                appointment_id,
                client=client,
                usage_indicator=_usage_indicator(),
                user_sub=user_sub,
            )
        except ClaimSubmissionPrereqError as exc:
            status = 404 if exc.code == "APPOINTMENT_NOT_FOUND" else 422
            details = {"errors": exc.errors} if exc.errors else None
            raise HTTPException(
                status_code=status,
                detail=ApiError(
                    error=Error(code=exc.code, message=exc.message, details=details)
                ).model_dump(by_alias=True),
            ) from exc
        return _to_schema(claim)


@router.get("/appointments/{appointment_id}/claim", response_model=list[Claim])
async def list_appointment_claims(appointment_id: uuid.UUID, request: Request) -> list[Claim]:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        rows = (
            await session.scalars(
                select(ClaimModel)
                .where(
                    ClaimModel.appointment_id == appointment_id,
                    ClaimModel.practice_id == practice_id,
                    ClaimModel.deleted_at.is_(None),
                )
                .order_by(ClaimModel.created_at.desc())
            )
        ).all()
        return [_to_schema(r) for r in rows]


@router.get("/claims/{claim_id}", response_model=Claim)
async def get_claim(claim_id: uuid.UUID, request: Request) -> Claim:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        row = await session.scalar(
            select(ClaimModel).where(
                ClaimModel.id == claim_id,
                ClaimModel.practice_id == practice_id,
                ClaimModel.deleted_at.is_(None),
            )
        )
        if row is None:
            raise _err(404, "CLAIM_NOT_FOUND", "Claim not found")
        return _to_schema(row)


@router.get("/claims", response_model=list[Claim])
async def list_claims(request: Request, status: ClaimStatus | None = None) -> list[Claim]:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        stmt = select(ClaimModel).where(
            ClaimModel.practice_id == practice_id,
            ClaimModel.deleted_at.is_(None),
        )
        if status:
            stmt = stmt.where(ClaimModel.status == status)
        rows = (await session.scalars(stmt.order_by(ClaimModel.created_at.desc()))).all()
        return [_to_schema(r) for r in rows]
