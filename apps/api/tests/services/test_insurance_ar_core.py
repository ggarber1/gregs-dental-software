import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.reports.insurance_ar import (
    WorklistRow,
    age_bucket,
    classify,
    is_underpaid,
    reason_for,
    summarize,
)


def test_age_bucket_boundaries():
    assert age_bucket(0) == "0-30"
    assert age_bucket(30) == "0-30"
    assert age_bucket(31) == "31-60"
    assert age_bucket(60) == "31-60"
    assert age_bucket(61) == "61-90"
    assert age_bucket(90) == "61-90"
    assert age_bucket(91) == "90+"


def test_is_underpaid_threshold():
    # exactly 95% of estimate -> NOT underpaid
    assert is_underpaid(950, 1000) is False
    # just under 95% -> underpaid
    assert is_underpaid(949, 1000) is True
    # large shortfall -> underpaid
    assert is_underpaid(200, 1000) is True
    # paid above estimate -> not underpaid
    assert is_underpaid(1200, 1000) is False


def test_is_underpaid_requires_both_numbers():
    assert is_underpaid(None, 1000) is False
    assert is_underpaid(500, None) is False
    assert is_underpaid(500, 0) is False


def _classify(status, paid=None, estimate=None, reviewed=None):
    return classify(
        status=status,
        insurance_paid_cents=paid,
        estimated_insurance_cents=estimate,
        insurance_reviewed_at=reviewed,
    )


def test_classify_draft_excluded():
    assert _classify("draft") is None


def test_classify_appealing_first_even_with_payment():
    # appealing wins even though there's a prior payment that looks underpaid
    assert _classify("appealing", paid=200, estimate=1000) == "appealing"


def test_classify_problem_statuses():
    assert _classify("denied", paid=0, estimate=1000) == "problem"
    assert _classify("clearinghouse_rejected") == "problem"
    assert _classify("submission_failed") == "problem"


def test_classify_awaiting_when_no_payment():
    assert _classify("submitted") == "awaiting"
    assert _classify("acknowledged") == "awaiting"
    assert _classify("pending") == "awaiting"


def test_classify_underpaid_keys_off_numbers_not_label():
    # labeled "paid" but paid far below estimate -> still underpaid (robust to bad label)
    assert _classify("paid", paid=200, estimate=1000) == "underpaid"
    assert _classify("partially_paid", paid=200, estimate=1000) == "underpaid"


def test_classify_paid_as_expected_is_done():
    assert _classify("paid", paid=1000, estimate=1000) is None
    assert _classify("partially_paid", paid=960, estimate=1000) is None


def test_classify_no_estimate_never_underpaid():
    assert _classify("paid", paid=200, estimate=None) is None


def test_classify_reviewed_drops_to_done():
    reviewed = datetime(2026, 6, 29, tzinfo=UTC)
    assert _classify("partially_paid", paid=200, estimate=1000, reviewed=reviewed) is None


def test_reason_denied_uses_codes():
    claim = SimpleNamespace(status="denied", denial_codes=["45", "B7"],
                            submission_errors=None, clearinghouse_status=None)
    assert reason_for(claim) == "denied: 45, B7"


def test_reason_rejected_uses_submission_errors():
    claim = SimpleNamespace(
        status="clearinghouse_rejected",
        denial_codes=None,
        submission_errors=["Missing tooth number"],
        clearinghouse_status="rejected",
    )
    assert reason_for(claim) == "Missing tooth number"


def test_reason_none_for_non_problem():
    claim = SimpleNamespace(
        status="submitted",
        denial_codes=None,
        submission_errors=None,
        clearinghouse_status=None,
    )
    assert reason_for(claim) is None


def _row(payer_id, category, bucket, billed, estimate=None, has_estimate=True):
    return WorklistRow(
        claim_id=uuid.uuid4(),
        appointment_id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        claim_number="PCN1",
        patient_name="Jane Doe",
        payer_id=payer_id,
        carrier_name=payer_id,
        category=category,
        billed_cents=billed,
        estimated_insurance_cents=estimate,
        insurance_paid_cents=None,
        shortfall_cents=None,
        has_estimate=has_estimate,
        days_out=10,
        bucket=bucket,
        status="submitted",
        reason=None,
    )


def test_summarize_aggregates_awaiting_by_carrier_and_bucket():
    rows = [
        _row("DELTA", "awaiting", "0-30", 1000, estimate=700),
        _row("DELTA", "awaiting", "61-90", 500, estimate=400),
        _row("DELTA", "underpaid", "0-30", 999, estimate=900),   # not aged into buckets
        _row("DELTA", "problem", "0-30", 300, has_estimate=False),
        _row("DELTA", "appealing", "0-30", 500),                 # claim_count only
        _row("METLIFE", "awaiting", "0-30", 800, estimate=None, has_estimate=False),
    ]
    summary = summarize(rows)

    delta = next(c for c in summary.carriers if c.payer_id == "DELTA")
    assert delta.claim_count == 5               # awaiting x2 + underpaid + problem + appealing
    assert delta.buckets.b0_30 == 1000          # only awaiting rows counted in buckets
    assert delta.buckets.b61_90 == 500
    assert delta.total_billed_cents == 1500     # awaiting only
    assert delta.expected_cents == 1100         # 700 + 400 (estimated awaiting only)
    assert delta.underpaid_count == 1
    assert delta.problem_count == 1
    assert delta.unestimated_count == 0         # both awaiting rows had estimates

    metlife = next(c for c in summary.carriers if c.payer_id == "METLIFE")
    assert metlife.claim_count == 1
    assert metlife.total_billed_cents == 800
    assert metlife.expected_cents == 0          # no estimate -> excluded from expected
    assert metlife.unestimated_count == 1

    # TOTAL row across carriers
    assert summary.totals.claim_count == 6
    assert summary.totals.total_billed_cents == 2300
    assert summary.totals.expected_cents == 1100
    assert summary.totals.underpaid_count == 1
    assert summary.totals.problem_count == 1
    assert summary.totals.unestimated_count == 1


def test_summarize_empty():
    summary = summarize([])
    assert summary.carriers == []
    assert summary.totals.claim_count == 0
    assert summary.totals.total_billed_cents == 0
    assert summary.totals.expected_cents == 0
    assert summary.totals.unestimated_count == 0
    assert summary.totals.underpaid_count == 0
    assert summary.totals.problem_count == 0
