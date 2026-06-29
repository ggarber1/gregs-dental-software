from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.reports.insurance_ar import age_bucket, classify, is_underpaid, reason_for


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
    claim = SimpleNamespace(status="submitted", denial_codes=None,
                            submission_errors=None, clearinghouse_status=None)
    assert reason_for(claim) is None
