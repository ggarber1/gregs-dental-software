from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt
from app.models.appointment import Appointment
from app.models.appointment_procedure import AppointmentProcedure
from app.models.claim import Claim
from app.models.insurance_plan import InsurancePlan
from app.models.ledger_entry import LedgerEntry
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


@dataclass
class _ClaimPrereqs:
    appt: Any
    patient: Any
    insurance: Any
    plan: Any
    provider: Any
    practice: Any
    billing_tax_id: str


async def _load_claim_prereqs(
    session: AsyncSession,
    practice_id: uuid.UUID,
    appointment_id: uuid.UUID,
) -> _ClaimPrereqs:
    """Load all DB objects required to build and submit a claim."""
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

    # 2. Load primary insurance.
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

    # 3. Load patient.
    patient = await session.scalar(select(Patient).where(Patient.id == appt.patient_id))
    if patient is None:
        raise ClaimSubmissionPrereqError("PATIENT_NOT_FOUND", "Patient not found")

    # 4. Load plan.
    plan = await session.scalar(
        select(InsurancePlan).where(InsurancePlan.id == insurance.insurance_plan_id)
    )
    if plan is None:
        raise ClaimSubmissionPrereqError(
            "INSURANCE_PLAN_NOT_FOUND", "Linked insurance plan not found"
        )

    # 5. Load provider.
    provider = await session.scalar(select(Provider).where(Provider.id == appt.provider_id))
    if provider is None:
        raise ClaimSubmissionPrereqError("NO_PROVIDER", "Rendering provider not found")

    # 6. Load practice and config checks.
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

    return _ClaimPrereqs(
        appt=appt,
        patient=patient,
        insurance=insurance,
        plan=plan,
        provider=provider,
        practice=practice,
        billing_tax_id=billing_tax_id,
    )


async def _reverse_claim_ledger_entries(
    session: AsyncSession,
    claim_id: uuid.UUID,
    remittance_id: uuid.UUID,
    user_sub: str | None,
) -> None:
    """Post reversing ledger entries for all non-reversed entries on a denied claim.

    Reversals are added to the session but not committed — the caller commits.
    """
    entries = (
        await session.scalars(
            select(LedgerEntry).where(
                LedgerEntry.claim_id == claim_id,
                LedgerEntry.remittance_id == remittance_id,
                LedgerEntry.reverses_entry_id.is_(None),
                LedgerEntry.deleted_at.is_(None),
            )
        )
    ).all()

    for entry in entries:
        reversal = LedgerEntry(
            practice_id=entry.practice_id,
            patient_id=entry.patient_id,
            entry_type=entry.entry_type,
            amount_cents=-entry.amount_cents,
            claim_id=entry.claim_id,
            remittance_id=entry.remittance_id,
            reverses_entry_id=entry.id,
            posted_by=user_sub or "system",
            memo=f"reversed on resubmission of claim {claim_id}",
        )
        session.add(reversal)


async def submit_claim_for_appointment(
    session: AsyncSession,
    practice_id: uuid.UUID,
    appointment_id: uuid.UUID,
    *,
    client: ClearinghouseClient,
    usage_indicator: str,
    user_sub: str | None,
) -> Claim:
    prereqs = await _load_claim_prereqs(session, practice_id, appointment_id)
    appt = prereqs.appt
    insurance = prereqs.insurance
    patient = prereqs.patient
    plan = prereqs.plan
    provider = prereqs.provider
    practice = prereqs.practice
    billing_tax_id = prereqs.billing_tax_id

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

    # 5. Build and validate the claim input.
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

    # 6. Persist a draft BEFORE the network call so a crash leaves a retryable record.
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

    # 7. Submit.
    try:
        result = await client.submit_dental_claim(claim_input, idempotency_key)
    except ClaimSubmissionError as exc:
        claim.status = "submission_failed"
        claim.submission_errors = [str(exc)]
        await session.commit()
        await session.refresh(claim)
        return claim

    # 8. Apply result.
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


_RESUBMITTABLE_STATUSES = {"clearinghouse_rejected", "submission_failed", "denied", "appealing"}


async def resubmit_claim(
    session: AsyncSession,
    practice_id: uuid.UUID,
    claim_id: uuid.UUID,
    *,
    client: ClearinghouseClient,
    usage_indicator: str,
    user_sub: str | None,
    post_to_ledger: bool = False,
) -> Claim:
    """Resubmit a previously submitted or denied claim.

    - clearinghouse_rejected / submission_failed → frequency code "1" (original)
    - denied / appealing → frequency code "7" (corrected), prior attempt snapshotted
    """
    # 1. Load the existing claim.
    claim = await session.scalar(
        select(Claim).where(
            Claim.id == claim_id,
            Claim.practice_id == practice_id,
            Claim.deleted_at.is_(None),
        )
    )
    if claim is None:
        raise ClaimSubmissionPrereqError("CLAIM_NOT_FOUND", "Claim not found")

    # 2. Check status is resubmittable.
    if claim.status not in _RESUBMITTABLE_STATUSES:
        raise ClaimSubmissionPrereqError(
            "CLAIM_NOT_RESUBMITTABLE",
            f"Claim status '{claim.status}' is not resubmittable",
        )

    # 3. Snapshot prior attempt.
    snapshot = {
        "attempt": claim.submission_attempt,
        "status": claim.status,
        "denialCodes": claim.denial_codes,
        "payerCcn": claim.payer_claim_control_number,
        "submittedAt": claim.submitted_at.isoformat() if claim.submitted_at else None,
    }
    claim.submission_history = list(claim.submission_history or []) + [snapshot]

    # 4. Determine frequency code and clear denial state if applicable.
    if claim.status in {"denied", "appealing"}:
        frequency_code = "7"
        original_claim_reference = claim.payer_claim_control_number
        if post_to_ledger and claim.remittance_id is not None:
            await _reverse_claim_ledger_entries(
                session, claim.id, claim.remittance_id, user_sub
            )
        claim.remittance_id = None
        claim.insurance_paid_cents = None
        claim.patient_responsibility_cents = None
        claim.denial_codes = None
        claim.paid_at = None
        claim.adjustments = None
    else:
        original_claim_reference = None
        frequency_code = "1"

    # 5. Increment attempt counter and set frequency code.
    new_attempt = claim.submission_attempt + 1
    claim.submission_attempt = new_attempt
    claim.claim_frequency_code = frequency_code

    # 6. Load prereqs (appointment, insurance, patient, plan, provider, practice).
    prereqs = await _load_claim_prereqs(session, practice_id, claim.appointment_id)

    # 7. Generate new PCN and idempotency key for this attempt.
    new_pcn = generate_pcn(str(claim.id), attempt=new_attempt)
    new_idempotency_key = generate_claim_idempotency_key(
        str(claim.appointment_id),
        str(prereqs.appt.patient_id),
        str(prereqs.insurance.id),
        new_attempt,
    )
    claim.patient_control_number = new_pcn
    claim.idempotency_key = new_idempotency_key

    # 8. Load procedures.
    procedures = (
        await session.scalars(
            select(AppointmentProcedure).where(
                AppointmentProcedure.appointment_id == claim.appointment_id,
                AppointmentProcedure.deleted_at.is_(None),
            )
        )
    ).all()
    if not procedures:
        raise ClaimSubmissionPrereqError("NO_PROCEDURES", "Appointment has no procedures")

    # 9. Build and validate claim input.
    claim_input = build_claim_input(
        appt=prereqs.appt,
        procedures=list(procedures),
        patient=prereqs.patient,
        insurance=prereqs.insurance,
        payer_id=prereqs.plan.payer_id,
        practice=prereqs.practice,
        provider=prereqs.provider,
        billing_tax_id=prereqs.billing_tax_id,
        pcn=new_pcn,
        usage_indicator=usage_indicator,
        claim_frequency_code=frequency_code,
        original_claim_reference=original_claim_reference,
    )

    validation = validate_claim(claim_input)
    if not validation.valid:
        raise ClaimSubmissionPrereqError(
            "CLAIM_INVALID", "Claim failed validation", errors=validation.errors
        )

    # 10. Update claim metadata and commit before network call.
    claim.total_charge_cents = claim_input.total_charge_cents
    claim.last_accessed_by = user_sub
    claim.last_accessed_at = datetime.now(UTC)
    await session.commit()

    # 11. Submit to clearinghouse.
    try:
        result = await client.submit_dental_claim(claim_input, new_idempotency_key)
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
        claim.submission_errors = None
    else:
        claim.status = "clearinghouse_rejected"
        claim.submission_errors = result.errors
    await session.commit()
    await session.refresh(claim)
    return claim


_WRITABLE_STATUSES = {"denied", "appealing"}


async def write_off_claim(
    session: AsyncSession,
    practice_id: uuid.UUID,
    claim_id: uuid.UUID,
    *,
    memo: str | None,
    user_sub: str | None,
) -> Any:  # LedgerEntry | None
    """Write off a denied/appealing claim: post an adjustment zeroing remaining balance.

    Sets insurance_reviewed_at so the claim moves to Done in the A/R worklist.
    Returns the new LedgerEntry, or None if the balance was already zero.
    """
    claim = await session.scalar(
        select(Claim).where(
            Claim.id == claim_id,
            Claim.practice_id == practice_id,
            Claim.deleted_at.is_(None),
        )
    )
    if claim is None:
        raise ClaimSubmissionPrereqError("CLAIM_NOT_FOUND", "Claim not found")
    if claim.status not in _WRITABLE_STATUSES:
        raise ClaimSubmissionPrereqError(
            "CLAIM_NOT_WRITABLE",
            f"Claim status '{claim.status}' cannot be written off",
        )
    if claim.insurance_reviewed_at is not None:
        raise ClaimSubmissionPrereqError("ALREADY_RESOLVED", "Claim is already resolved")

    # Compute remaining balance attributable to this claim.
    remaining: int = await session.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).where(
            LedgerEntry.claim_id == claim_id,
            LedgerEntry.practice_id == practice_id,
            LedgerEntry.deleted_at.is_(None),
        )
    ) or 0

    entry = None
    if remaining > 0:
        entry = LedgerEntry(
            id=uuid.uuid4(),
            practice_id=claim.practice_id,
            patient_id=claim.patient_id,
            entry_type="adjustment",
            amount_cents=-remaining,
            claim_id=claim.id,
            memo=memo or "insurance denial write-off",
            posted_by=user_sub or "system",
        )
        session.add(entry)

    claim.insurance_reviewed_at = datetime.now(UTC)
    claim.last_accessed_by = user_sub
    claim.last_accessed_at = datetime.now(UTC)
    await session.commit()
    if entry is not None:
        await session.refresh(entry)
    return entry
