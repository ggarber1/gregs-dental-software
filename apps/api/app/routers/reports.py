from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request

from app.core.db import get_session_factory
from app.core.features import require_feature
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import (
    ApiError,
    ClaimActionResult,
    Error,
    InsuranceARRow,
    InsuranceARSummary,
)
from app.services.reports import insurance_ar

router = APIRouter(prefix="/api/v1", tags=["reports"])
_FEATURE = "claims_submission"


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=ApiError(error=Error(code=code, message=message)).model_dump(by_alias=True),
    )


def _row_to_dict(r: insurance_ar.WorklistRow) -> dict[str, Any]:
    # Keyed by the generated aliases (camelCase) for aliased fields and the bare
    # names for the rest; category/bucket/status pass plain strings that Pydantic
    # coerces into their enums during model_validate.
    return {
        "claimId": r.claim_id,
        "claimNumber": r.claim_number,
        "patientName": r.patient_name,
        "payerId": r.payer_id,
        "carrierName": r.carrier_name,
        "category": r.category,
        "billedCents": r.billed_cents,
        "estimatedInsuranceCents": r.estimated_insurance_cents,
        "insurancePaidCents": r.insurance_paid_cents,
        "shortfallCents": r.shortfall_cents,
        "hasEstimate": r.has_estimate,
        "daysOut": r.days_out,
        "bucket": r.bucket,
        "status": r.status,
        "reason": r.reason,
    }


def _buckets_to_dict(b: insurance_ar.Buckets) -> dict[str, Any]:
    return {"b0_30": b.b0_30, "b31_60": b.b31_60, "b61_90": b.b61_90, "b90_plus": b.b90_plus}


@router.get("/reports/insurance-ar/claims", response_model=list[InsuranceARRow])
async def get_insurance_ar_worklist(
    request: Request,
    category: str | None = None,
    payer_id: str | None = None,
    bucket: str | None = None,
    status: str | None = None,
    sort: Literal["oldest", "newest"] = "oldest",
) -> list[InsuranceARRow]:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        rows = await insurance_ar.get_worklist(
            session,
            practice_id,
            category=category,
            payer_id=payer_id,
            bucket=bucket,
            status=status,
            sort=sort,
        )
        return [InsuranceARRow.model_validate(_row_to_dict(r)) for r in rows]


@router.get("/reports/insurance-ar/summary", response_model=InsuranceARSummary)
async def get_insurance_ar_summary(request: Request) -> InsuranceARSummary:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        s = await insurance_ar.get_summary(session, practice_id)
        carriers = [
            {
                "payerId": c.payer_id,
                "carrierName": c.carrier_name,
                "claimCount": c.claim_count,
                "buckets": _buckets_to_dict(c.buckets),
                "totalBilledCents": c.total_billed_cents,
                "expectedCents": c.expected_cents,
                "unestimatedCount": c.unestimated_count,
                "underpaidCount": c.underpaid_count,
                "problemCount": c.problem_count,
            }
            for c in s.carriers
        ]
        totals = {
            "claimCount": s.totals.claim_count,
            "buckets": _buckets_to_dict(s.totals.buckets),
            "totalBilledCents": s.totals.total_billed_cents,
            "expectedCents": s.totals.expected_cents,
            "unestimatedCount": s.totals.unestimated_count,
            "underpaidCount": s.totals.underpaid_count,
            "problemCount": s.totals.problem_count,
        }
        return InsuranceARSummary.model_validate({"carriers": carriers, "totals": totals})


def _action_result(claim: Any) -> ClaimActionResult:
    return ClaimActionResult.model_validate(
        {
            "claimId": claim.id,
            "status": claim.status,
            "insuranceReviewedAt": claim.insurance_reviewed_at,
        }
    )


@router.post(
    "/reports/insurance-ar/claims/{claim_id}/accept",
    response_model=ClaimActionResult,
)
async def accept_underpayment(claim_id: uuid.UUID, request: Request) -> ClaimActionResult:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        try:
            claim = await insurance_ar.accept_underpayment(session, practice_id, claim_id)
        except LookupError:
            raise _err(404, "CLAIM_NOT_FOUND", "Claim not found") from None
        except ValueError:
            raise _err(409, "NOT_UNDERPAID", "Claim is not currently underpaid") from None
        return _action_result(claim)


@router.post(
    "/reports/insurance-ar/claims/{claim_id}/appeal",
    response_model=ClaimActionResult,
)
async def flag_for_appeal(claim_id: uuid.UUID, request: Request) -> ClaimActionResult:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        try:
            claim = await insurance_ar.flag_for_appeal(session, practice_id, claim_id)
        except LookupError:
            raise _err(404, "CLAIM_NOT_FOUND", "Claim not found") from None
        except ValueError:
            raise _err(409, "NOT_UNDERPAID", "Claim is not currently underpaid") from None
        return _action_result(claim)
