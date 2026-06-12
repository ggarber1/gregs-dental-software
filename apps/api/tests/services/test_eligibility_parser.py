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


# ---------------------------------------------------------------------------
# New tests — lock in first-wins, whole-number percent, and empty payloads
# ---------------------------------------------------------------------------

def test_family_deductible_parsed():
    """FAM deductible is stored and IND is left None when absent."""
    payload = {
        "benefitsInformation": [
            {
                "code": "C",
                "coverageLevelCode": "FAM",
                "benefitAmount": "200.00",
            },
        ]
    }
    r = parse_stedi_response(payload)
    assert r.deductible_family == 20000
    assert r.deductible_individual is None


def test_annual_max_used_parsed():
    """code=F entry whose additionalInformation description contains 'used' maps to annual_max_individual_used."""
    payload = {
        "benefitsInformation": [
            {
                "code": "F",
                "coverageLevelCode": "IND",
                "benefitAmount": "300.00",
                "additionalInformation": [{"description": "Amount used"}],
            },
        ]
    }
    r = parse_stedi_response(payload)
    assert r.annual_max_individual_used == 30000


def test_empty_payload_is_unknown():
    """Empty dict and benefitsInformation=None both yield UNKNOWN status with no money/coins."""
    r_empty = parse_stedi_response({})
    assert r_empty.status == EligibilityStatus.UNKNOWN
    assert r_empty.deductible_individual is None
    assert r_empty.coinsurance_basic is None

    r_none = parse_stedi_response({"benefitsInformation": None})
    assert r_none.status == EligibilityStatus.UNKNOWN
    assert r_none.deductible_individual is None
    assert r_none.coinsurance_basic is None


def test_whole_number_percent_normalized():
    """benefitPercent='80' (insurance pays 80%) → coinsurance_major == 0.20."""
    payload = {
        "benefitsInformation": [
            {
                "code": "A",
                "name": "Co-Insurance",
                "benefitPercent": "80",
                "additionalInformation": [{"description": "Major - insurance pays"}],
            },
        ]
    }
    r = parse_stedi_response(payload)
    assert r.coinsurance_major == 0.20


def test_duplicate_deductible_keeps_first():
    """First-wins: two IND deductible entries; only the first value is kept."""
    payload = {
        "benefitsInformation": [
            {"code": "C", "coverageLevelCode": "IND", "benefitAmount": "50.00"},
            {"code": "C", "coverageLevelCode": "IND", "benefitAmount": "75.00"},
        ]
    }
    r = parse_stedi_response(payload)
    assert r.deductible_individual == 5000


def test_plan_name_falls_back_to_network_id_description():
    # Cigna-style: no planDescription; plan name lives in planNetworkIdDescription.
    payload = {
        "planInformation": {
            "groupDescription": "DENTAL GROUP",
            "planNetworkIdDescription": "TOTAL CIGNA DPPO",
        },
        "benefitsInformation": [{"code": "1", "name": "Active Coverage"}],
    }
    assert parse_stedi_response(payload).plan_name == "TOTAL CIGNA DPPO"


def test_additional_information_null_or_object_does_not_crash():
    payload = {
        "benefitsInformation": [
            {"code": "1", "name": "Active Coverage", "additionalInformation": None},
            {
                "code": "A", "name": "Co-Insurance", "benefitPercent": "0.30",
                "additionalInformation": {"description": "Preventive services"},
            },
        ]
    }
    r = parse_stedi_response(payload)
    assert r.status == EligibilityStatus.ACTIVE
    # single-object additionalInformation is coerced; preventive 0.30 stays patient-share
    assert r.coinsurance_preventive == 0.30
