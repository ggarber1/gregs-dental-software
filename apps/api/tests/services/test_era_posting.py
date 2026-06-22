from app.services.era.base import ClaimAdjustment, ClaimPayment
from app.services.era.posting import claim_payment_fields, status_for_claim_payment


def _cp(status: str, pr_cents: int = 0, adjustments=()) -> ClaimPayment:
    return ClaimPayment(
        patient_control_number="ABC",
        claim_status_code=status,
        total_charge_cents=25000,
        paid_cents=20000,
        patient_responsibility_cents=pr_cents,
        payer_claim_control_number="P-1",
        adjustments=adjustments,
    )


def test_processed_with_no_patient_responsibility_is_paid():
    assert status_for_claim_payment(_cp("1", pr_cents=0)) == "paid"


def test_processed_with_patient_responsibility_is_partially_paid():
    assert status_for_claim_payment(_cp("1", pr_cents=5000)) == "partially_paid"


def test_forwarded_codes_are_processed():
    assert status_for_claim_payment(_cp("19", pr_cents=0)) == "paid"
    assert status_for_claim_payment(_cp("20", pr_cents=5000)) == "partially_paid"


def test_denied_code_is_denied():
    assert status_for_claim_payment(_cp("4")) == "denied"


def test_reversal_code_is_denied():
    assert status_for_claim_payment(_cp("22")) == "denied"


def test_zero_paid_but_processed_is_not_denied():
    # CLP02=1 with $0 paid is still an accepted claim — never infer 'denied' from amount.
    cp = ClaimPayment(
        patient_control_number="ABC", claim_status_code="1", total_charge_cents=25000,
        paid_cents=0, patient_responsibility_cents=0, payer_claim_control_number=None,
    )
    assert status_for_claim_payment(cp) == "paid"


def test_fields_map_cents_and_adjustments_and_denial_codes():
    cp = _cp(
        "4",
        adjustments=(
            ClaimAdjustment(group="PR", code="2", cents=5000),
            ClaimAdjustment(group="CO", code="45", cents=3000),
        ),
    )
    fields = claim_payment_fields(cp)
    assert fields["insurance_paid_cents"] == 20000
    assert fields["patient_responsibility_cents"] == 0
    assert fields["payer_claim_control_number"] == "P-1"
    assert fields["adjustments"] == [
        {"group": "PR", "code": "2", "cents": 5000},
        {"group": "CO", "code": "45", "cents": 3000},
    ]
    # denial_codes only populated on denied claims, from CARC reason codes
    assert fields["denial_codes"] == ["2", "45"]


def test_denial_codes_empty_when_not_denied():
    cp = _cp("1", adjustments=(ClaimAdjustment(group="CO", code="45", cents=3000),))
    assert claim_payment_fields(cp)["denial_codes"] is None
