from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from app.core.db import get_session_factory
from app.core.features import require_feature
from app.routers.patients import _require_practice_scope
from app.schemas.generated import (
    ApiError,
    Buckets,
    Carrier,
    Error,
    InsuranceARRow,
    InsuranceARSummary,
    Totals1,
)
from app.services.reports import insurance_ar

router = APIRouter(prefix="/api/v1", tags=["reports"])
_FEATURE = "claims_submission"


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=ApiError(error=Error(code=code, message=message)).model_dump(by_alias=True),
    )


def _row_to_schema(r: insurance_ar.WorklistRow) -> InsuranceARRow:
    return InsuranceARRow(
        claimId=r.claim_id,
        claimNumber=r.claim_number,
        patientName=r.patient_name,
        payerId=r.payer_id,
        carrierName=r.carrier_name,
        category=r.category,
        billedCents=r.billed_cents,
        estimatedInsuranceCents=r.estimated_insurance_cents,
        insurancePaidCents=r.insurance_paid_cents,
        shortfallCents=r.shortfall_cents,
        hasEstimate=r.has_estimate,
        daysOut=r.days_out,
        bucket=r.bucket,
        status=r.status,
        reason=r.reason,
    )


def _buckets_to_schema(b: insurance_ar.Buckets) -> Buckets:
    return Buckets(b0_30=b.b0_30, b31_60=b.b31_60, b61_90=b.b61_90, b90_plus=b.b90_plus)


@router.get("/reports/insurance-ar/claims", response_model=list[InsuranceARRow])
async def get_insurance_ar_worklist(
    request: Request,
    category: str | None = None,
    payer_id: str | None = None,
    bucket: str | None = None,
    status: str | None = None,
    sort: str = "oldest",
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
        return [_row_to_schema(r) for r in rows]


@router.get("/reports/insurance-ar/summary", response_model=InsuranceARSummary)
async def get_insurance_ar_summary(request: Request) -> InsuranceARSummary:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        s = await insurance_ar.get_summary(session, practice_id)
        carriers = [
            Carrier(
                payerId=c.payer_id,
                carrierName=c.carrier_name,
                claimCount=c.claim_count,
                buckets=_buckets_to_schema(c.buckets),
                totalBilledCents=c.total_billed_cents,
                expectedCents=c.expected_cents,
                unestimatedCount=c.unestimated_count,
                underpaidCount=c.underpaid_count,
                problemCount=c.problem_count,
            )
            for c in s.carriers
        ]
        totals = Totals1(
            claimCount=s.totals.claim_count,
            buckets=_buckets_to_schema(s.totals.buckets),
            totalBilledCents=s.totals.total_billed_cents,
            expectedCents=s.totals.expected_cents,
            unestimatedCount=s.totals.unestimated_count,
            underpaidCount=s.totals.underpaid_count,
            problemCount=s.totals.problem_count,
        )
        return InsuranceARSummary(carriers=carriers, totals=totals)
