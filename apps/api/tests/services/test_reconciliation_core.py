from app.services.reports.reconciliation import classify_for_reconciliation


def test_overpaid():
    assert classify_for_reconciliation(1100, 1000) == "overpaid"


def test_matched_exact():
    assert classify_for_reconciliation(1000, 1000) == "matched"


def test_within_tolerance_just_under():
    # 949/1000 = 94.9% — underpaid, returns None
    assert classify_for_reconciliation(949, 1000) is None


def test_within_tolerance_at_95_pct():
    # exactly 95% — NOT underpaid, within tolerance
    assert classify_for_reconciliation(950, 1000) == "within_tolerance"


def test_within_tolerance_between_95_and_100():
    assert classify_for_reconciliation(980, 1000) == "within_tolerance"


def test_no_estimate_none():
    assert classify_for_reconciliation(800, None) == "no_estimate"


def test_no_estimate_zero():
    # zero estimate treated as no estimate (avoid divide-by-zero)
    assert classify_for_reconciliation(800, 0) == "no_estimate"


def test_large_underpayment_excluded():
    assert classify_for_reconciliation(100, 1000) is None


def test_zero_paid_no_estimate():
    assert classify_for_reconciliation(0, None) == "no_estimate"
