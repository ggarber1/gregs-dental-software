from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt
from app.models.appointment import Appointment
from app.models.appointment_procedure import AppointmentProcedure
from app.models.claim import Claim
from app.models.insurance_plan import InsurancePlan
from app.models.patient import Patient
from app.models.patient_insurance import PatientInsurance
from app.models.practice import Practice
from app.models.provider import Provider
from app.services.claims.base import ClaimSubmissionError, ClearinghouseClient
from app.services.claims.builder import build_claim_input
from app.services.claims.idempotency import generate_claim_idempotency_key, generate_pcn
from app.services.claims.validator import validate_claim


class ClaimSubmissionPrereqError(Exception):
    """A prerequisite for building/submitting a claim is missing or invalid."""

    def __init__(self, code: str, message: str, *, errors: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.errors = errors or []


async def submit_claim_for_appointment(
    session: AsyncSession,
    practice_id: uuid.UUID,
    appointment_id: uuid.UUID,
    *,
    client: ClearinghouseClient,
    usage_indicator: str,
    user_sub: str | None,
) -> Claim:
    # 1. Load appointment (scope to practice_id, deleted_at null).
    appt = await session.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.practice_id == practice_id,
            Appointment.deleted_at.is_(None),
        )
    )
    if appt is None or appt.patient_id is None:
        raise ClaimSubmissionPrereqError("APPOINTMENT_NOT_FOUND", "Appointment not found")
    if appt.provider_id is None:
        raise ClaimSubmissionPrereqError(
            "NO_PROVIDER", "Appointment has no provider; a rendering provider is required"
        )

    # 2. Load primary insurance (needed to compute the deterministic key).
    insurance = await session.scalar(
        select(PatientInsurance).where(
            PatientInsurance.patient_id == appt.patient_id,
            PatientInsurance.practice_id == practice_id,
            PatientInsurance.priority == "primary",
            PatientInsurance.deleted_at.is_(None),
        )
    )
    if insurance is None or insurance.insurance_plan_id is None:
        raise ClaimSubmissionPrereqError(
            "NO_INSURANCE", "Patient has no primary insurance with a linked plan"
        )

    # 3. Compute deterministic idempotency key and check for an existing claim.
    #    A re-click returns the same claim — no second submission to the payer.
    #    Recovering a 'submission_failed' claim (transient transport error) is
    #    deferred to Module 7b's status reconciliation.
    idempotency_key = generate_claim_idempotency_key(
        str(appointment_id), str(appt.patient_id), str(insurance.id), 1
    )
    existing = await session.scalar(
        select(Claim).where(
            Claim.idempotency_key == idempotency_key,
            Claim.practice_id == practice_id,
        )
    )
    if existing is not None:
        return existing

    # 4. Load procedures.
    procedures = (
        await session.scalars(
            select(AppointmentProcedure).where(
                AppointmentProcedure.appointment_id == appointment_id,
                AppointmentProcedure.deleted_at.is_(None),
            )
        )
    ).all()
    if not procedures:
        raise ClaimSubmissionPrereqError("NO_PROCEDURES", "Appointment has no procedures")

    # 5. Load patient.
    patient = await session.scalar(select(Patient).where(Patient.id == appt.patient_id))
    if patient is None:
        raise ClaimSubmissionPrereqError("PATIENT_NOT_FOUND", "Patient not found")

    # 6. Load plan.
    plan = await session.scalar(
        select(InsurancePlan).where(InsurancePlan.id == insurance.insurance_plan_id)
    )
    if plan is None:
        raise ClaimSubmissionPrereqError(
            "INSURANCE_PLAN_NOT_FOUND", "Linked insurance plan not found"
        )

    # 7. Load provider.
    provider = await session.scalar(select(Provider).where(Provider.id == appt.provider_id))
    if provider is None:
        raise ClaimSubmissionPrereqError("NO_PROVIDER", "Rendering provider not found")

    # 8. Load practice and config checks.
    practice = await session.scalar(select(Practice).where(Practice.id == practice_id))
    if practice is None or not practice.billing_npi:
        raise ClaimSubmissionPrereqError("MISSING_NPI", "Practice billing NPI is not configured")
    if not practice.clearinghouse_submitter_id:
        raise ClaimSubmissionPrereqError(
            "MISSING_CLEARINGHOUSE", "Clearinghouse submitter ID is not configured"
        )
    if not practice.billing_tax_id_encrypted:
        raise ClaimSubmissionPrereqError(
            "MISSING_TAX_ID", "Practice billing tax ID is not configured"
        )
    billing_tax_id = decrypt(practice.billing_tax_id_encrypted)

    # 9. Build and validate the claim input.
    claim_id = uuid.uuid4()
    pcn = generate_pcn(str(claim_id))
    claim_input = build_claim_input(
        appt=appt,
        procedures=list(procedures),
        patient=patient,
        insurance=insurance,
        payer_id=plan.payer_id,
        practice=practice,
        provider=provider,
        billing_tax_id=billing_tax_id,
        pcn=pcn,
        usage_indicator=usage_indicator,
    )

    validation = validate_claim(claim_input)
    if not validation.valid:
        raise ClaimSubmissionPrereqError(
            "CLAIM_INVALID", "Claim failed validation", errors=validation.errors
        )

    # 10. Persist a draft BEFORE the network call so a crash leaves a retryable record.
    claim = Claim(
        id=claim_id,
        practice_id=practice_id,
        appointment_id=appointment_id,
        patient_id=patient.id,
        insurance_id=insurance.id,
        provider_id=provider.id,
        idempotency_key=idempotency_key,
        patient_control_number=pcn,
        payer_id=plan.payer_id,
        status="draft",
        total_charge_cents=claim_input.total_charge_cents,
        last_accessed_by=user_sub,
        last_accessed_at=datetime.now(UTC),
    )
    session.add(claim)
    await session.commit()

    # NOTE: at-least-once. If the process dies after submit_dental_claim returns but
    # before the commit below, the claim stays 'draft' though the clearinghouse accepted
    # it; a retry with the same idempotency key returns the stale draft. Module 7b's
    # status reconciliation closes this gap.

    # 11. Submit.
    try:
        result = await client.submit_dental_claim(claim_input, idempotency_key)
    except ClaimSubmissionError as exc:
        claim.status = "submission_failed"
        claim.submission_errors = [str(exc)]
        await session.commit()
        await session.refresh(claim)
        return claim

    # 12. Apply result.
    claim.raw_submission = result.raw_request
    claim.raw_response = result.raw_response
    claim.clearinghouse_claim_id = result.clearinghouse_claim_id
    claim.clearinghouse_status = result.clearinghouse_status
    if result.accepted:
        claim.status = "submitted"
        claim.submitted_at = datetime.now(UTC)
    else:
        claim.status = "clearinghouse_rejected"
        claim.submission_errors = result.errors
    await session.commit()
    await session.refresh(claim)
    return claim
