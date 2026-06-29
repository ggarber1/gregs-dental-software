from app.services.reports.insurance_ar import age_bucket, is_underpaid


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
