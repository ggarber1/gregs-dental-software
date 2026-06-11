from __future__ import annotations

from datetime import date

from app.services.eligibility.base import BenefitCategory, EligibilityStatus
from app.services.eligibility.parser import parse_stedi_response

_ACTIVE_FULL = {
    "payer": {"name": "Delta Dental"},
    "planInformation": {"planDescription": "PPO Basic"},
    "planDateInformation": {"planBegin": "20260101", "planEnd": "20261231"},
    "benefitsInformation": [
        {"code": "1", "name": "Active Coverage", "serviceTypeCodes": ["35"]},
        {
            "code": "C", "name": "Deductible", "coverageLevelCode": "IND",
            "benefitAmount": "50.00", "additionalInformation": [{"description": "Calendar year"}],
        },
        {
            "code": "F", "name": "Limitations", "coverageLevelCode": "IND",
            "timeQualifierCode": "23", "benefitAmount": "1500.00",
        },
        {
            "code": "F", "name": "Limitations", "coverageLevelCode": "IND",
            "timeQualifierCode": "29", "benefitAmount": "1200.00",
        },
        {
            "code": "A", "name": "Co-Insurance", "benefitPercent": "0.20",
            "additionalInformation": [{"description": "Preventive services"}],
        },
        {
            "code": "A", "name": "Co-Insurance", "benefitPercent": "0.80",
            "additionalInformation": [{"description": "Major - insurance pays"}],
        },
    ],
}


def test_parse_active_status_and_dates():
    r = parse_stedi_response(_ACTIVE_FULL)
    assert r.status == EligibilityStatus.ACTIVE
    assert r.payer_name == "Delta Dental"
    assert r.plan_name == "PPO Basic"
    assert r.coverage_start_date == date(2026, 1, 1)
    assert r.coverage_end_date == date(2026, 12, 31)


def test_parse_money_to_cents():
    r = parse_stedi_response(_ACTIVE_FULL)
    assert r.deductible_individual == 5000
    assert r.annual_max_individual == 150000
    assert r.annual_max_individual_remaining == 120000


def test_coinsurance_patient_share_both_conventions():
    r = parse_stedi_response(_ACTIVE_FULL)
    assert r.coinsurance_preventive == 0.20
    assert r.coinsurance_major == 0.20


def test_missing_fields_are_none_not_zero():
    minimal = {"benefitsInformation": [{"code": "6", "name": "Inactive"}]}
    r = parse_stedi_response(minimal)
    assert r.status == EligibilityStatus.INACTIVE
    assert r.deductible_individual is None
    assert r.annual_max_individual is None
    assert r.coinsurance_basic is None


def test_ortho_detected_from_description():
    payload = {
        "benefitsInformation": [
            {"code": "1", "name": "Active Coverage"},
            {
                "code": "A", "name": "Co-Insurance", "benefitPercent": "0.50",
                "additionalInformation": [{"description": "Orthodontic treatment"}],
            },
        ]
    }
    r = parse_stedi_response(payload)
    assert r.coinsurance_ortho == 0.50
