from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.core.db import get_session_factory
from app.core.features import require_feature
from app.core.ssm import get_ssm_parameter
from app.models.eligibility_check import EligibilityCheck as CheckModel
from app.models.insurance_plan import InsurancePlan as PlanModel
from app.models.patient import Patient as PatientModel
from app.models.patient_insurance import PatientInsurance as InsuranceModel
from app.models.practice import Practice as PracticeModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import ApiError, CreateEligibilityCheck, EligibilityCheck, Error
from app.services.eligibility.base import (
    EligibilityProviderError,
    EligibilityRequest,
    EligibilityResult,
)
from app.services.eligibility.stedi import StediProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/eligibility", tags=["eligibility"])

_FEATURE = "eligibility_verification"


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=ApiError(error=Error(code=code, message=message)).model_dump(by_alias=True),
    )


def _row_to_schema(row: CheckModel) -> EligibilityCheck:
    def coins(v: object) -> float | None:
        return float(v) if v is not None else None

    return EligibilityCheck(
        id=row.id,
        practiceId=row.practice_id,
        patientId=row.patient_id,
        patientInsuranceId=row.patient_insurance_id,
        appointmentId=row.appointment_id,
        idempotencyKey=row.idempotency_key,
        status=row.status,  # type: ignore[arg-type]
        trigger=row.trigger,  # type: ignore[arg-type]
        clearinghouse=row.clearinghouse,
        payerIdUsed=row.payer_id_used,
        payerName=row.payer_name,
        planName=row.plan_name,
        failureReason=row.failure_reason,
        coverageStatus=row.coverage_status,  # type: ignore[arg-type]
        coverageStartDate=row.coverage_start_date,
        coverageEndDate=row.coverage_end_date,
        deductibleIndividual=row.deductible_individual,
        deductibleIndividualMet=row.deductible_individual_met,
        deductibleFamily=row.deductible_family,
        deductibleFamilyMet=row.deductible_family_met,
        oopMaxIndividual=row.oop_max_individual,
        oopMaxIndividualMet=row.oop_max_individual_met,
        annualMaxIndividual=row.annual_max_individual,
        annualMaxIndividualUsed=row.annual_max_individual_used,
        annualMaxIndividualRemaining=row.annual_max_individual_remaining,
        coinsurancePreventive=coins(row.coinsurance_preventive),
        coinsuranceBasic=coins(row.coinsurance_basic),
        coinsuranceMajor=coins(row.coinsurance_major),
        coinsuranceOrtho=coins(row.coinsurance_ortho),
        waitingPeriodBasicMonths=row.waiting_period_basic_months,
        waitingPeriodMajorMonths=row.waiting_period_major_months,
        waitingPeriodOrthoMonths=row.waiting_period_ortho_months,
        frequencyLimits=row.frequency_limits,
        requestedAt=(row.requested_at or row.created_at or datetime.now(UTC)).replace(tzinfo=UTC),
        verifiedAt=row.verified_at.replace(tzinfo=UTC) if row.verified_at else None,
        failedAt=row.failed_at.replace(tzinfo=UTC) if row.failed_at else None,
        createdAt=(row.created_at or datetime.now(UTC)).replace(tzinfo=UTC),
        updatedAt=(row.updated_at or datetime.now(UTC)).replace(tzinfo=UTC),
    )


def _apply_result(row: CheckModel, result: EligibilityResult) -> None:
    row.status = "verified"
    row.coverage_status = result.status.value
    row.payer_name = result.payer_name
    row.plan_name = result.plan_name
    row.coverage_start_date = result.coverage_start_date
    row.coverage_end_date = result.coverage_end_date
    row.deductible_individual = result.deductible_individual
    row.deductible_individual_met = result.deductible_individual_met
    row.deductible_family = result.deductible_family
    row.deductible_family_met = result.deductible_family_met
    row.oop_max_individual = result.oop_max_individual
    row.oop_max_individual_met = result.oop_max_individual_met
    row.annual_max_individual = result.annual_max_individual
    row.annual_max_individual_used = result.annual_max_individual_used
    row.annual_max_individual_remaining = result.annual_max_individual_remaining
    row.coinsurance_preventive = result.coinsurance_preventive
    row.coinsurance_basic = result.coinsurance_basic
    row.coinsurance_major = result.coinsurance_major
    row.coinsurance_ortho = result.coinsurance_ortho
    row.waiting_period_basic_months = result.waiting_period_basic_months
    row.waiting_period_major_months = result.waiting_period_major_months
    row.waiting_period_ortho_months = result.waiting_period_ortho_months
    row.frequency_limits = result.frequency_limits
    row.raw_response = result.raw_response
    row.verified_at = datetime.now(UTC)


@router.post("/check", status_code=201, response_model=EligibilityCheck)
async def create_eligibility_check(
    body: CreateEligibilityCheck, request: Request
) -> EligibilityCheck:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    idempotency_key = request.headers.get("Idempotency-Key") or str(uuid.uuid4())

    async with get_session_factory()() as session:
        # Fetch practice first — one scalar that also gives us features, billing_npi, ssm path.
        practice = await session.scalar(
            select(PracticeModel).where(PracticeModel.id == practice_id)
        )

        await require_feature(session, practice_id, _FEATURE, practice=practice)

        insurance = await session.scalar(
            select(InsuranceModel).where(
                InsuranceModel.id == body.patient_insurance_id,
                InsuranceModel.practice_id == practice_id,
                InsuranceModel.deleted_at.is_(None),
            )
        )
        if insurance is None:
            raise _err(404, "INSURANCE_NOT_FOUND", "Insurance record not found")
        if insurance.insurance_plan_id is None:
            raise _err(
                422,
                "NO_PAYER_ID",
                "This insurance has no linked plan/payer ID; link an insurance plan first",
            )

        plan = await session.scalar(
            select(PlanModel).where(
                PlanModel.id == insurance.insurance_plan_id,
                PlanModel.practice_id == practice_id,
            )
        )
        if plan is None:
            raise _err(422, "NO_PAYER_ID", "Linked insurance plan not found")

        if insurance.relationship_to_insured == "self":
            patient = await session.scalar(
                select(PatientModel).where(PatientModel.id == insurance.patient_id)
            )
            if patient is None:
                raise _err(404, "PATIENT_NOT_FOUND", "Patient not found")
            first, last, dob = patient.first_name, patient.last_name, patient.date_of_birth
        else:
            first = insurance.insured_first_name or ""
            last = insurance.insured_last_name or ""
            dob = insurance.insured_date_of_birth

        if not dob:
            raise _err(422, "MISSING_SUBSCRIBER_DOB", "Subscriber date of birth is required")

        if not practice.billing_npi:
            raise _err(422, "MISSING_NPI", "Practice billing NPI is not configured")
        if not practice.clearinghouse_api_key_ssm_path:
            raise _err(
                422, "MISSING_CLEARINGHOUSE", "Clearinghouse credentials are not configured"
            )

        row = CheckModel(
            id=uuid.uuid4(),
            practice_id=practice_id,
            patient_id=insurance.patient_id,
            patient_insurance_id=insurance.id,
            appointment_id=body.appointment_id,
            idempotency_key=idempotency_key,
            status="pending",
            trigger="manual",
            clearinghouse="stedi",
            payer_id_used=plan.payer_id,
            requested_at=datetime.now(UTC),
        )

        api_key = get_ssm_parameter(practice.clearinghouse_api_key_ssm_path)
        if not api_key:
            row.status = "failed"
            row.failure_reason = "Clearinghouse API key unavailable"
            row.failed_at = datetime.now(UTC)
        else:
            provider = StediProvider(api_key=api_key)
            elig_request = EligibilityRequest(
                payer_id=plan.payer_id,
                subscriber_id=insurance.member_id or "",
                group_number=insurance.group_number,
                subscriber_dob=dob,
                subscriber_first_name=first,
                subscriber_last_name=last,
                provider_npi=practice.billing_npi,
                submitter_id=practice.clearinghouse_submitter_id,
                date_of_service=datetime.now(UTC).date(),
                control_number=str(uuid.uuid4().int)[:9],
            )
            try:
                result = await provider.check_eligibility(elig_request)
                _apply_result(row, result)
            except EligibilityProviderError as exc:
                row.status = "not_supported" if exc.not_supported else "failed"
                row.failure_reason = str(exc)
                row.failed_at = datetime.now(UTC)

        session.add(row)
        await session.commit()
        await session.refresh(row)
        return _row_to_schema(row)


@router.get("/{check_id}", response_model=EligibilityCheck)
async def get_eligibility_check(check_id: uuid.UUID, request: Request) -> EligibilityCheck:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        row = await session.scalar(
            select(CheckModel).where(
                CheckModel.id == check_id,
                CheckModel.practice_id == practice_id,
                CheckModel.deleted_at.is_(None),
            )
        )
        if row is None:
            raise _err(404, "ELIGIBILITY_CHECK_NOT_FOUND", "Eligibility check not found")
        return _row_to_schema(row)


@router.get("", response_model=list[EligibilityCheck])
async def list_eligibility_checks(
    patient_id: uuid.UUID, request: Request
) -> list[EligibilityCheck]:
    """Latest check per patient_insurance_id for the patient (feeds the chart card)."""
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        rows = (
            await session.scalars(
                select(CheckModel)
                .where(
                    CheckModel.patient_id == patient_id,
                    CheckModel.practice_id == practice_id,
                    CheckModel.deleted_at.is_(None),
                )
                .order_by(CheckModel.created_at.desc())
            )
        ).all()
    latest: dict[uuid.UUID, CheckModel] = {}
    for r in rows:
        latest.setdefault(r.patient_insurance_id, r)
    return [_row_to_schema(r) for r in latest.values()]
