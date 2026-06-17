from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment as AppointmentModel
from app.models.appointment_procedure import AppointmentProcedure as ProcedureModel
from app.models.appointment_procedure import CdtCode as CdtCodeModel
from app.models.contracted_fee_schedule import ContractedFeeSchedule as ContractedModel
from app.models.copay_calculation import CopayCalculation as CalcModel
from app.models.eligibility_check import EligibilityCheck as CheckModel
from app.services.copay.engine import calculate_patient_responsibility
from app.services.copay.models import EligibilitySnapshot, PlanType, ProcedureInput, ProcedureResult

_CATEGORY_COINSURANCE_FIELD = {
    "preventive": "coinsurance_preventive",
    "diagnostic": "coinsurance_preventive",
    "basic": "coinsurance_basic",
    "major": "coinsurance_major",
    "ortho": "coinsurance_ortho",
}


class CopayCalculationError(Exception):
    """Raised when prerequisites are missing (no procedures / no verified eligibility)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _line_item_json(li: ProcedureResult) -> dict[str, Any]:
    """Serialize a ProcedureResult to the camelCase shape CopayLineItem expects."""
    return {
        "procedureId": li.procedure_id,
        "cdtCode": li.cdt_code,
        "category": li.category,
        "providerFeeCents": li.provider_fee_cents,
        "allowedAmountCents": li.allowed_amount_cents,
        "writeOffCents": li.write_off_cents,
        "deductibleAppliedCents": li.deductible_applied_cents,
        "insuranceOwesCents": li.insurance_owes_cents,
        "patientOwesCents": li.patient_owes_cents,
        "needsManualEntry": li.needs_manual_entry,
        "notCovered": li.not_covered,
        "isFrequencyExceeded": li.is_frequency_exceeded,
        "isInWaitingPeriod": li.is_in_waiting_period,
        "annualMaxCapApplied": li.annual_max_cap_applied,
    }


async def _latest_verified_check(
    session: AsyncSession, practice_id: uuid.UUID, patient_id: uuid.UUID
) -> CheckModel | None:
    return cast(
        CheckModel | None,
        await session.scalar(
            select(CheckModel)
            .where(
                CheckModel.practice_id == practice_id,
                CheckModel.patient_id == patient_id,
                CheckModel.status == "verified",
                CheckModel.deleted_at.is_(None),
            )
            .order_by(CheckModel.created_at.desc())
        ),
    )


def _resolve_coinsurance(check: CheckModel, code: str, category: str) -> float | None:
    by_code = check.coinsurance_by_code or {}
    if code in by_code:
        return float(by_code[code])
    field = _CATEGORY_COINSURANCE_FIELD.get(category)
    if field is None:
        return None
    val = getattr(check, field)
    return float(val) if val is not None else None


def _waived_categories(check: CheckModel) -> frozenset[str]:
    waived: set[str] = set()
    if check.deductible_waived_diagnostic:
        waived.add("diagnostic")
    if check.deductible_waived_preventive:
        waived.add("preventive")
    if check.deductible_waived_orthodontic:
        waived.add("ortho")
    return frozenset(waived)


def _waiting_period_map(check: CheckModel) -> dict[str, int]:
    out: dict[str, int] = {}
    if check.waiting_period_basic_months is not None:
        out["basic"] = check.waiting_period_basic_months
    if check.waiting_period_major_months is not None:
        out["major"] = check.waiting_period_major_months
    if check.waiting_period_ortho_months is not None:
        out["ortho"] = check.waiting_period_ortho_months
    return out


def _snapshot(check: CheckModel) -> EligibilitySnapshot:
    ded_total = check.deductible_individual or 0
    ded_met = check.deductible_individual_met or 0
    annual_remaining = check.annual_max_individual_remaining
    if annual_remaining is None and check.annual_max_individual is not None:
        annual_remaining = check.annual_max_individual - (check.annual_max_individual_used or 0)
    ortho_remaining: int | None = None
    if check.ortho_lifetime_max is not None:
        ortho_remaining = max(0, check.ortho_lifetime_max - (check.ortho_lifetime_max_used or 0))
    try:
        plan_type = PlanType(check.plan_type)
    except ValueError:
        plan_type = PlanType.PPO
    return EligibilitySnapshot(
        plan_type=plan_type,
        network_status=check.network_status,
        coverage_start_date=check.coverage_start_date,
        deductible_remaining_cents=max(0, ded_total - ded_met),
        deductible_waived_categories=_waived_categories(check),
        annual_max_remaining_cents=annual_remaining,
        ortho_lifetime_max_remaining_cents=ortho_remaining,
        waiting_period_months_by_category=_waiting_period_map(check),
        has_secondary_insurance=False,
    )


async def _frequency_used(
    session: AsyncSession,
    practice_id: uuid.UUID,
    patient_id: uuid.UUID,
    appointment_id: uuid.UUID,
    code: str,
) -> int:
    """Best-effort count from completed procedure history (claims history lands in M7).
    Counts this calendar year, excluding the current appointment."""
    year_start = date(date.today().year, 1, 1)
    rows = await session.scalars(
        select(ProcedureModel.id).where(
            ProcedureModel.practice_id == practice_id,
            ProcedureModel.patient_id == patient_id,
            ProcedureModel.appointment_id != appointment_id,
            ProcedureModel.procedure_code == code,
            ProcedureModel.deleted_at.is_(None),
            ProcedureModel.created_at >= year_start,
        )
    )
    return len(rows.all())


async def calculate_for_appointment(
    session: AsyncSession,
    practice_id: uuid.UUID,
    appointment_id: uuid.UUID,
    user_sub: str | None,
) -> CalcModel:
    appt = await session.scalar(
        select(AppointmentModel).where(
            AppointmentModel.id == appointment_id,
            AppointmentModel.practice_id == practice_id,
            AppointmentModel.deleted_at.is_(None),
        )
    )
    if appt is None or appt.patient_id is None:
        raise CopayCalculationError("APPOINTMENT_NOT_FOUND", "Appointment not found")

    procs = (
        await session.scalars(
            select(ProcedureModel).where(
                ProcedureModel.appointment_id == appointment_id,
                ProcedureModel.deleted_at.is_(None),
            )
        )
    ).all()
    if not procs:
        raise CopayCalculationError("NO_PROCEDURES", "Appointment has no procedures to estimate")

    check = await _latest_verified_check(session, practice_id, appt.patient_id)
    if check is None:
        raise CopayCalculationError(
            "NO_ELIGIBILITY", "No verified eligibility check for this patient"
        )

    payer_id = check.payer_id_used

    cdt_ids = [p.cdt_code_id for p in procs if p.cdt_code_id is not None]
    cdt_by_id: dict[uuid.UUID, CdtCodeModel] = {}
    if cdt_ids:
        for c in (
            await session.scalars(select(CdtCodeModel).where(CdtCodeModel.id.in_(cdt_ids)))
        ).all():
            cdt_by_id[c.id] = c

    inputs: list[ProcedureInput] = []
    for p in procs:
        cdt = cdt_by_id.get(p.cdt_code_id) if p.cdt_code_id else None
        code = (cdt.code if cdt else p.procedure_code) or ""
        category = cdt.category if cdt else "other"
        contracted: ContractedModel | None = None
        if p.cdt_code_id is not None:
            contracted = await session.scalar(
                select(ContractedModel).where(
                    ContractedModel.practice_id == practice_id,
                    ContractedModel.payer_id == payer_id,
                    ContractedModel.cdt_code_id == p.cdt_code_id,
                    ContractedModel.deleted_at.is_(None),
                )
            )
        freq_used = await _frequency_used(
            session, practice_id, appt.patient_id, appointment_id, code
        )
        inputs.append(
            ProcedureInput(
                procedure_id=str(p.id),
                cdt_code=code,
                category=category,
                provider_fee_cents=p.fee_cents,
                allowed_amount_cents=contracted.allowed_amount_cents if contracted else None,
                coinsurance_patient_share=_resolve_coinsurance(check, code, category),
                not_covered=bool(contracted.not_covered) if contracted else False,
                requires_prior_auth=(
                    bool(contracted.requires_prior_auth) if contracted else False
                ),
                frequency_limit_count=(check.frequency_limits or {}).get(code, {}).get("count"),
                frequency_used_count=freq_used,
            )
        )

    service_date = appt.start_time.date() if appt.start_time else date.today()
    breakdown = calculate_patient_responsibility(_snapshot(check), inputs, service_date)

    by_proc = {li.procedure_id: li for li in breakdown.line_items}
    for p in procs:
        li = by_proc.get(str(p.id))
        if li is not None:
            p.insurance_est_cents = li.insurance_owes_cents
            p.patient_est_cents = li.patient_owes_cents
            p.estimate_source = "eligibility"

    idem = hashlib.sha256(
        f"{appointment_id}|{check.id}|{sorted(str(p.id) for p in procs)}".encode()
    ).hexdigest()

    existing = await session.scalar(select(CalcModel).where(CalcModel.idempotency_key == idem))
    calc = existing or CalcModel(id=uuid.uuid4(), idempotency_key=idem)
    calc.practice_id = practice_id
    calc.patient_id = appt.patient_id
    calc.appointment_id = appointment_id
    calc.eligibility_check_id = check.id
    calc.calculated_at = datetime.now(UTC)
    calc.plan_type = breakdown.plan_type.value
    calc.total_provider_fee_cents = breakdown.total_provider_fee_cents
    calc.total_write_off_cents = breakdown.total_write_off_cents
    calc.total_insurance_owes_cents = breakdown.total_insurance_owes_cents
    calc.total_patient_owes_cents = breakdown.total_patient_owes_cents
    calc.deductible_remaining_after_cents = breakdown.deductible_remaining_after_cents
    calc.annual_max_remaining_after_cents = breakdown.annual_max_remaining_after_cents
    calc.has_secondary_insurance = breakdown.has_secondary_insurance
    calc.line_items = [_line_item_json(li) for li in breakdown.line_items]
    calc.last_accessed_by = user_sub
    calc.last_accessed_at = datetime.now(UTC)
    if existing is None:
        session.add(calc)
    await session.commit()
    await session.refresh(calc)
    return calc
