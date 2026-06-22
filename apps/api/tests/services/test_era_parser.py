from datetime import date

from app.services.era.parser import parse_stedi_era

# Modeled on the documented Stedi/CHC-Convert 835 JSON shape (see parser external-contract note).
_PAID = {
    "meta": {"transactionId": "txn-1"},
    "transactions": [
        {
            "financialInformation": {"totalActualProviderPaymentAmount": "200.00"},
            "reassociationTraceNumber": {"checkOrEftTraceNumber": "EFT123"},
            "productionDate": "20260615",
            "payer": {"name": "DELTA DENTAL"},
            "detailInfo": [
                {
                    "paymentInfo": [
                        {
                            "claimPaymentInfo": {
                                "patientControlNumber": "ABC123",
                                "claimStatusCode": "1",
                                "totalClaimChargeAmount": "250.00",
                                "claimPaymentAmount": "200.00",
                                "patientResponsibilityAmount": "50.00",
                                "payerClaimControlNumber": "PAYER-9",
                            },
                            "claimAdjustments": [
                                {
                                    "claimAdjustmentGroupCode": "PR",
                                    "adjustmentDetails": [
                                        {"adjustmentReasonCode": "2", "adjustmentAmount": "50.00"}
                                    ],
                                }
                            ],
                        }
                    ]
                }
            ],
        }
    ],
}

_DENIED = {
    "meta": {"transactionId": "txn-2"},
    "transactions": [
        {
            "payer": {"name": "AETNA"},
            "detailInfo": [
                {
                    "paymentInfo": [
                        {
                            "claimPaymentInfo": {
                                "patientControlNumber": "DEN999",
                                "claimStatusCode": "4",
                                "totalClaimChargeAmount": "300.00",
                                "claimPaymentAmount": "0.00",
                                "patientResponsibilityAmount": "0.00",
                                "payerClaimControlNumber": "P-1",
                            },
                            "claimAdjustments": [
                                {
                                    "claimAdjustmentGroupCode": "CO",
                                    "adjustmentDetails": [
                                        {"adjustmentReasonCode": "29", "adjustmentAmount": "300.00"}
                                    ],
                                }
                            ],
                        }
                    ]
                }
            ],
        }
    ],
}


def test_parses_payer_trace_date_and_total():
    era = parse_stedi_era(_PAID)
    assert era.payer_name == "DELTA DENTAL"
    assert era.trace_number == "EFT123"
    assert era.payment_date == date(2026, 6, 15)
    assert era.payment_cents == 20000


def test_parses_claim_payment_to_cents():
    era = parse_stedi_era(_PAID)
    assert len(era.claim_payments) == 1
    cp = era.claim_payments[0]
    assert cp.patient_control_number == "ABC123"
    assert cp.claim_status_code == "1"
    assert cp.total_charge_cents == 25000
    assert cp.paid_cents == 20000
    assert cp.patient_responsibility_cents == 5000
    assert cp.payer_claim_control_number == "PAYER-9"


def test_parses_adjustments():
    cp = parse_stedi_era(_PAID).claim_payments[0]
    assert len(cp.adjustments) == 1
    adj = cp.adjustments[0]
    assert adj.group == "PR"
    assert adj.code == "2"
    assert adj.cents == 5000


def test_denied_claim_status_preserved():
    cp = parse_stedi_era(_DENIED).claim_payments[0]
    assert cp.claim_status_code == "4"
    assert cp.paid_cents == 0


def test_multi_claim_remittance():
    doc = {
        "transactions": [
            {
                "detailInfo": [
                    {
                        "paymentInfo": [
                            _PAID["transactions"][0]["detailInfo"][0]["paymentInfo"][0],
                            _DENIED["transactions"][0]["detailInfo"][0]["paymentInfo"][0],
                        ]
                    }
                ]
            }
        ]
    }
    era = parse_stedi_era(doc)
    assert len(era.claim_payments) == 2


def test_missing_fields_do_not_crash():
    era = parse_stedi_era({"transactions": [{"detailInfo": [{"paymentInfo": [{}]}]}]})
    assert len(era.claim_payments) == 1
    cp = era.claim_payments[0]
    assert cp.patient_control_number == ""
    assert cp.paid_cents == 0


def test_parses_iso_date_format():
    doc = {"transactions": [{"productionDate": "2026-06-15", "detailInfo": []}]}
    assert parse_stedi_era(doc).payment_date == date(2026, 6, 15)


def test_missing_payer_claim_control_number_is_none():
    era = parse_stedi_era({"transactions": [{"detailInfo": [{"paymentInfo": [{}]}]}]})
    assert era.claim_payments[0].payer_claim_control_number is None
