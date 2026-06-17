from __future__ import annotations

from datetime import date

from app.services.copay.engine import calculate_patient_responsibility
from app.services.copay.models import EligibilitySnapshot, PlanType, ProcedureInput

SVC = date(2026, 6, 16)


def _snap(**kw):
    base = dict(
        plan_type=PlanType.PPO,
        network_status="in_network",
        coverage_start_date=date(2020, 1, 1),
        deductible_remaining_cents=0,
        deductible_waived_categories=frozenset({"preventive", "diagnostic"}),
        annual_max_remaining_cents=200000,
        ortho_lifetime_max_remaining_cents=None,
        waiting_period_months_by_category={},
        has_secondary_insurance=False,
    )
    base.update(kw)
    return EligibilitySnapshot(**base)


def _assert_identity(result):
    for li in result.line_items:
        assert (
            li.write_off_cents + li.patient_owes_cents + li.insurance_owes_cents
            == li.provider_fee_cents
        ), li


def test_ortho_draws_lifetime_bucket_not_annual_max():
    # Ortho insurance is capped by the ortho lifetime max, and does NOT consume the
    # annual max (which stays available for other categories).
    proc = ProcedureInput(
        procedure_id="o1", cdt_code="D8080", category="ortho",
        provider_fee_cents=300000, allowed_amount_cents=300000, coinsurance_patient_share=0.50,
    )
    snap = _snap(
        deductible_remaining_cents=0,
        annual_max_remaining_cents=200000,
        ortho_lifetime_max_remaining_cents=150000,
    )
    r = calculate_patient_responsibility(snap, [proc], SVC)
    li = r.line_items[0]
    assert li.insurance_owes_cents == 150000          # 50% of 300000, fits the lifetime cap
    assert li.patient_owes_cents == 150000
    assert r.annual_max_remaining_after_cents == 200000  # annual max untouched by ortho
    _assert_identity(r)


def test_ortho_lifetime_cap_overflows_to_patient():
    proc = ProcedureInput(
        procedure_id="o1", cdt_code="D8080", category="ortho",
        provider_fee_cents=300000, allowed_amount_cents=300000, coinsurance_patient_share=0.50,
    )
    snap = _snap(
        deductible_remaining_cents=0,
        annual_max_remaining_cents=200000,
        ortho_lifetime_max_remaining_cents=100000,
    )
    r = calculate_patient_responsibility(snap, [proc], SVC)
    li = r.line_items[0]
    assert li.annual_max_cap_applied is True
    assert li.insurance_owes_cents == 100000          # capped at ortho lifetime remaining
    assert li.patient_owes_cents == 200000            # 150000 coinsurance + 50000 overflow
    assert r.annual_max_remaining_after_cents == 200000
    _assert_identity(r)


def test_ortho_falls_back_to_annual_max_when_no_lifetime_returned():
    # When the plan returns no ortho lifetime max, ortho uses the annual max bucket.
    proc = ProcedureInput(
        procedure_id="o1", cdt_code="D8080", category="ortho",
        provider_fee_cents=100000, allowed_amount_cents=100000, coinsurance_patient_share=0.50,
    )
    snap = _snap(
        deductible_remaining_cents=0,
        annual_max_remaining_cents=200000,
        ortho_lifetime_max_remaining_cents=None,
    )
    r = calculate_patient_responsibility(snap, [proc], SVC)
    assert r.line_items[0].insurance_owes_cents == 50000
    assert r.annual_max_remaining_after_cents == 150000  # ortho drew the annual max
    _assert_identity(r)


def test_scenario2_basic_filling_fresh_deductible():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D2392", category="basic",
        provider_fee_cents=20000, allowed_amount_cents=18000, coinsurance_patient_share=0.20,
    )
    r = calculate_patient_responsibility(_snap(deductible_remaining_cents=5000), [proc], SVC)
    li = r.line_items[0]
    assert li.write_off_cents == 2000
    assert li.deductible_applied_cents == 5000
    assert li.insurance_owes_cents == 10400
    assert li.patient_owes_cents == 7600
    _assert_identity(r)


def test_scenario3_deductible_met():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D2392", category="basic",
        provider_fee_cents=20000, allowed_amount_cents=18000, coinsurance_patient_share=0.20,
    )
    r = calculate_patient_responsibility(_snap(deductible_remaining_cents=0), [proc], SVC)
    li = r.line_items[0]
    assert li.deductible_applied_cents == 0
    assert li.insurance_owes_cents == 14400
    assert li.patient_owes_cents == 3600
    _assert_identity(r)


def test_scenario1_preventive_zero_and_deductible_untouched():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D1110", category="preventive",
        provider_fee_cents=12000, allowed_amount_cents=12000, coinsurance_patient_share=0.00,
    )
    r = calculate_patient_responsibility(_snap(deductible_remaining_cents=5000), [proc], SVC)
    li = r.line_items[0]
    assert li.patient_owes_cents == 0
    assert li.deductible_applied_cents == 0
    assert r.deductible_remaining_after_cents == 5000
    _assert_identity(r)


def test_scenario7_deductible_splits_across_two_procedures():
    p1 = ProcedureInput(
        procedure_id="p1", cdt_code="D2391", category="basic",
        provider_fee_cents=3000, allowed_amount_cents=3000, coinsurance_patient_share=0.20,
    )
    p2 = ProcedureInput(
        procedure_id="p2", cdt_code="D2392", category="basic",
        provider_fee_cents=20000, allowed_amount_cents=20000, coinsurance_patient_share=0.20,
    )
    r = calculate_patient_responsibility(_snap(deductible_remaining_cents=5000), [p1, p2], SVC)
    by_id = {li.procedure_id: li for li in r.line_items}
    assert by_id["p1"].deductible_applied_cents == 3000
    assert by_id["p2"].deductible_applied_cents == 2000
    assert r.deductible_remaining_after_cents == 0
    _assert_identity(r)


def test_scenario4_annual_max_exhausted_mid_visit():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D2750", category="major",
        provider_fee_cents=80000, allowed_amount_cents=80000, coinsurance_patient_share=0.50,
    )
    r = calculate_patient_responsibility(
        _snap(deductible_remaining_cents=0, annual_max_remaining_cents=20000), [proc], SVC
    )
    li = r.line_items[0]
    assert li.annual_max_cap_applied is True
    assert li.insurance_owes_cents == 20000
    assert li.patient_owes_cents == 60000
    _assert_identity(r)


def test_scenario5_frequency_exceeded():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D1110", category="preventive",
        provider_fee_cents=12000, allowed_amount_cents=12000, coinsurance_patient_share=0.00,
        frequency_limit_count=2, frequency_used_count=2,
    )
    r = calculate_patient_responsibility(_snap(), [proc], SVC)
    li = r.line_items[0]
    assert li.is_frequency_exceeded is True
    assert li.insurance_owes_cents == 0
    assert li.patient_owes_cents == 12000
    _assert_identity(r)


def test_scenario6_waiting_period_blocks_coverage():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D2750", category="major",
        provider_fee_cents=80000, allowed_amount_cents=80000, coinsurance_patient_share=0.50,
    )
    snap = _snap(coverage_start_date=date(2026, 3, 16),
                 waiting_period_months_by_category={"major": 12})
    r = calculate_patient_responsibility(snap, [proc], SVC)
    li = r.line_items[0]
    assert li.is_in_waiting_period is True
    assert li.insurance_owes_cents == 0
    _assert_identity(r)


def test_scenario6b_waiting_period_zero_months_is_waived():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D2750", category="major",
        provider_fee_cents=80000, allowed_amount_cents=80000, coinsurance_patient_share=0.50,
    )
    snap = _snap(coverage_start_date=date(2026, 3, 16),
                 waiting_period_months_by_category={"major": 0})
    r = calculate_patient_responsibility(snap, [proc], SVC)
    assert r.line_items[0].is_in_waiting_period is False
    assert r.line_items[0].insurance_owes_cents > 0


def test_unknown_coinsurance_flags_manual():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D9999", category="other",
        provider_fee_cents=10000, allowed_amount_cents=10000, coinsurance_patient_share=None,
    )
    r = calculate_patient_responsibility(_snap(), [proc], SVC)
    assert r.line_items[0].needs_manual_entry is True


def test_scenario12_oon_balance_billing():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D2750", category="major",
        provider_fee_cents=140000, allowed_amount_cents=90000, coinsurance_patient_share=0.50,
    )
    snap = _snap(network_status="out_of_network", deductible_remaining_cents=0)
    r = calculate_patient_responsibility(snap, [proc], SVC)
    li = r.line_items[0]
    assert li.write_off_cents == 0
    assert li.insurance_owes_cents == 45000
    assert li.patient_owes_cents == 95000
    _assert_identity(r)


def test_scenario8_medicaid_patient_zero():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D1110", category="preventive",
        provider_fee_cents=12000, allowed_amount_cents=8000, coinsurance_patient_share=None,
    )
    r = calculate_patient_responsibility(_snap(plan_type=PlanType.MEDICAID), [proc], SVC)
    li = r.line_items[0]
    assert li.patient_owes_cents == 0
    assert li.insurance_owes_cents == 8000
    assert li.write_off_cents == 4000
    _assert_identity(r)


def test_scenario9_medicaid_not_covered_implant():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D6010", category="major",
        provider_fee_cents=200000, allowed_amount_cents=200000,
        coinsurance_patient_share=None, not_covered=True,
    )
    r = calculate_patient_responsibility(_snap(plan_type=PlanType.MEDICAID), [proc], SVC)
    li = r.line_items[0]
    assert li.not_covered is True
    assert li.insurance_owes_cents == 0
    assert li.patient_owes_cents == 200000
    _assert_identity(r)


def test_scenario13_secondary_insurance_flagged():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D2392", category="basic",
        provider_fee_cents=20000, allowed_amount_cents=20000, coinsurance_patient_share=0.20,
    )
    r = calculate_patient_responsibility(_snap(has_secondary_insurance=True), [proc], SVC)
    assert r.has_secondary_insurance is True


def test_negative_write_off_clamped():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D2392", category="basic",
        provider_fee_cents=10000, allowed_amount_cents=18000, coinsurance_patient_share=0.20,
    )
    r = calculate_patient_responsibility(_snap(deductible_remaining_cents=0), [proc], SVC)
    assert r.line_items[0].write_off_cents == 0
    _assert_identity(r)


def test_annual_max_exactly_zero_pays_nothing():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D2750", category="major",
        provider_fee_cents=80000, allowed_amount_cents=80000, coinsurance_patient_share=0.50,
    )
    r = calculate_patient_responsibility(
        _snap(deductible_remaining_cents=0, annual_max_remaining_cents=0), [proc], SVC
    )
    li = r.line_items[0]
    assert li.insurance_owes_cents == 0
    assert li.annual_max_cap_applied is True
    _assert_identity(r)


def test_totals_sum_line_items():
    p1 = ProcedureInput(
        procedure_id="p1", cdt_code="D1110", category="preventive",
        provider_fee_cents=12000, allowed_amount_cents=12000, coinsurance_patient_share=0.00,
    )
    p2 = ProcedureInput(
        procedure_id="p2", cdt_code="D2392", category="basic",
        provider_fee_cents=20000, allowed_amount_cents=18000, coinsurance_patient_share=0.20,
    )
    r = calculate_patient_responsibility(_snap(deductible_remaining_cents=5000), [p1, p2], SVC)
    assert r.total_provider_fee_cents == 32000
    assert (
        r.total_write_off_cents + r.total_patient_owes_cents + r.total_insurance_owes_cents
        == r.total_provider_fee_cents
    )
