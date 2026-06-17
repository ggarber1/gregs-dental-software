"""Pure co-pay calculation engine. Algorithm reference:
docs/billing/copay-calculation-algorithm.md. No I/O; all money integer cents."""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta

from app.services.copay.models import (
    CATEGORY_ORDER,
    EligibilitySnapshot,
    PatientResponsibilityBreakdown,
    PlanType,
    ProcedureInput,
    ProcedureResult,
)


def _round_cents(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _sort_key(proc: ProcedureInput) -> int:
    try:
        return CATEGORY_ORDER.index(proc.category)
    except ValueError:
        return len(CATEGORY_ORDER)


def calculate_patient_responsibility(
    snapshot: EligibilitySnapshot,
    procedures: list[ProcedureInput],
    service_date: date,
) -> PatientResponsibilityBreakdown:
    """Pure function. No I/O. Dispatches by plan type; OON is a branch in _standard."""
    if snapshot.plan_type == PlanType.MEDICAID:
        return _calculate_medicaid(snapshot, procedures, service_date)
    if snapshot.plan_type in (PlanType.PPO, PlanType.PREMIER, PlanType.INDEMNITY):
        return _calculate_standard(snapshot, procedures, service_date)
    return _calculate_unsupported(snapshot, procedures, service_date)


def _new_breakdown(
    snapshot: EligibilitySnapshot, service_date: date
) -> PatientResponsibilityBreakdown:
    return PatientResponsibilityBreakdown(
        service_date=service_date,
        plan_type=snapshot.plan_type,
        annual_max_remaining_after_cents=snapshot.annual_max_remaining_cents,
        has_secondary_insurance=snapshot.has_secondary_insurance,
    )


def _finalize(result: PatientResponsibilityBreakdown) -> PatientResponsibilityBreakdown:
    result.total_provider_fee_cents = sum(li.provider_fee_cents for li in result.line_items)
    result.total_write_off_cents = sum(li.write_off_cents for li in result.line_items)
    result.total_insurance_owes_cents = sum(li.insurance_owes_cents for li in result.line_items)
    result.total_patient_owes_cents = sum(li.patient_owes_cents for li in result.line_items)
    return result


def _calculate_standard(
    snapshot: EligibilitySnapshot,
    procedures: list[ProcedureInput],
    service_date: date,
) -> PatientResponsibilityBreakdown:
    result = _new_breakdown(snapshot, service_date)
    deductible_remaining = snapshot.deductible_remaining_cents
    annual_max_remaining = snapshot.annual_max_remaining_cents
    ortho_lifetime_remaining = snapshot.ortho_lifetime_max_remaining_cents

    for proc in sorted(procedures, key=_sort_key):
        fee = proc.provider_fee_cents
        oon = snapshot.network_status == "out_of_network"
        allowed = proc.allowed_amount_cents if proc.allowed_amount_cents is not None else fee
        # In-network: insurer can't pay above the provider fee; clamp the effective basis.
        effective = allowed if oon else min(fee, allowed)
        write_off = 0 if oon else max(0, fee - allowed)
        balance_bill = max(0, fee - allowed) if oon else 0

        li = ProcedureResult(
            procedure_id=proc.procedure_id, cdt_code=proc.cdt_code, category=proc.category,
            provider_fee_cents=fee, allowed_amount_cents=allowed,
            write_off_cents=write_off, deductible_applied_cents=0,
            insurance_owes_cents=0, patient_owes_cents=0,
        )

        if proc.not_covered:
            li.not_covered = True
            li.patient_owes_cents = effective + balance_bill
            result.line_items.append(li)
            continue
        if _in_waiting_period(snapshot, proc, service_date):
            li.is_in_waiting_period = True
            li.patient_owes_cents = effective + balance_bill
            result.line_items.append(li)
            continue
        if proc.frequency_limit_count is not None and (
            proc.frequency_used_count >= proc.frequency_limit_count
        ):
            li.is_frequency_exceeded = True
            li.patient_owes_cents = effective + balance_bill
            result.line_items.append(li)
            continue
        if proc.coinsurance_patient_share is None:
            li.needs_manual_entry = True
            result.line_items.append(li)
            continue

        amount = effective
        if proc.category not in snapshot.deductible_waived_categories:
            applied = min(deductible_remaining, amount)
            li.deductible_applied_cents = applied
            deductible_remaining -= applied
            amount -= applied

        patient_share = Decimal(str(proc.coinsurance_patient_share))
        gross_insurance = _round_cents(Decimal(amount) * (Decimal(1) - patient_share))
        patient_coins = amount - gross_insurance

        # Ortho draws its own lifetime maximum bucket (when the plan returns one);
        # every other category draws the annual maximum. Overflow goes to the patient.
        overflow = 0
        uses_ortho_bucket = proc.category == "ortho" and ortho_lifetime_remaining is not None
        cap = ortho_lifetime_remaining if uses_ortho_bucket else annual_max_remaining
        if cap is not None:
            capped = min(gross_insurance, cap)
            if capped < gross_insurance:
                li.annual_max_cap_applied = True
            overflow = gross_insurance - capped
            if uses_ortho_bucket:
                ortho_lifetime_remaining = cap - capped
            else:
                annual_max_remaining = cap - capped
            gross_insurance = capped

        li.insurance_owes_cents = gross_insurance
        li.patient_owes_cents = (
            li.deductible_applied_cents + patient_coins + overflow + balance_bill
        )
        result.line_items.append(li)

    result.deductible_remaining_after_cents = deductible_remaining
    result.annual_max_remaining_after_cents = annual_max_remaining
    return _finalize(result)


def _in_waiting_period(
    snapshot: EligibilitySnapshot, proc: ProcedureInput, service_date: date
) -> bool:
    months = snapshot.waiting_period_months_by_category.get(proc.category, 0) or 0
    if months <= 0 or snapshot.coverage_start_date is None:
        return False
    clears = snapshot.coverage_start_date + relativedelta(months=months)
    return service_date < clears


def _calculate_medicaid(
    snapshot: EligibilitySnapshot,
    procedures: list[ProcedureInput],
    service_date: date,
) -> PatientResponsibilityBreakdown:
    result = _new_breakdown(snapshot, service_date)
    for proc in procedures:
        fee = proc.provider_fee_cents
        allowed = proc.allowed_amount_cents if proc.allowed_amount_cents is not None else fee
        li = ProcedureResult(
            procedure_id=proc.procedure_id, cdt_code=proc.cdt_code, category=proc.category,
            provider_fee_cents=fee, allowed_amount_cents=allowed,
            write_off_cents=0, deductible_applied_cents=0,
            insurance_owes_cents=0, patient_owes_cents=0,
        )
        if proc.not_covered:
            li.not_covered = True
            li.patient_owes_cents = allowed
            li.write_off_cents = max(0, fee - allowed)
        else:
            li.insurance_owes_cents = allowed
            li.write_off_cents = max(0, fee - allowed)
        result.line_items.append(li)
    result.deductible_remaining_after_cents = snapshot.deductible_remaining_cents
    return _finalize(result)


def _calculate_unsupported(
    snapshot: EligibilitySnapshot,
    procedures: list[ProcedureInput],
    service_date: date,
) -> PatientResponsibilityBreakdown:
    # DHMO / unknown plan types: every line flagged for manual entry (deferred slice).
    result = _new_breakdown(snapshot, service_date)
    for proc in procedures:
        fee = proc.provider_fee_cents
        allowed = proc.allowed_amount_cents if proc.allowed_amount_cents is not None else fee
        li = ProcedureResult(
            procedure_id=proc.procedure_id, cdt_code=proc.cdt_code, category=proc.category,
            provider_fee_cents=fee, allowed_amount_cents=allowed,
            write_off_cents=0, deductible_applied_cents=0,
            insurance_owes_cents=0, patient_owes_cents=0, needs_manual_entry=True,
        )
        result.line_items.append(li)
    return _finalize(result)
