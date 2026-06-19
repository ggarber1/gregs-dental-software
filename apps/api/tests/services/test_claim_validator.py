from datetime import date

from app.services.claims.base import Address, ClaimLine, DentalClaimInput
from app.services.claims.validator import validate_claim


def _claim(**overrides) -> DentalClaimInput:
    base = dict(
        patient_control_number="ABC123",
        payer_id="CDLA1",
        usage_indicator="T",
        billing_npi="1234567890",
        billing_tax_id="123456789",
        billing_taxonomy_code="1223G0001X",
        billing_org_name="Downtown Dental",
        billing_address=Address(
            line1="1 Main St", city="Boston", state="MA", postal_code="021011234"
        ),
        submitter_id="SUB1",
        rendering_npi="1234567890",
        rendering_first_name="Jane",
        rendering_last_name="Dentist",
        subscriber_first_name="John",
        subscriber_last_name="Smith",
        subscriber_dob=date(1980, 1, 1),
        subscriber_gender="M",
        subscriber_address=Address(
            line1="2 Oak Ave", city="Boston", state="MA", postal_code="021022345"
        ),
        member_id="U123",
        group_number="GRP1",
        relationship_to_insured="self",
        patient_first_name="John",
        patient_last_name="Smith",
        patient_dob=date(1980, 1, 1),
        patient_gender="M",
        date_of_service=date(2026, 6, 18),
        lines=(
            ClaimLine(
                procedure_id="p1", cdt_code="D2392", fee_cents=20000,
                tooth_number="14", surface="O", procedure_name="Resin composite",
            ),
        ),
    )
    base.update(overrides)
    return DentalClaimInput(**base)


def test_valid_claim_has_no_errors():
    result = validate_claim(_claim())
    assert result.valid is True
    assert result.errors == []


def test_invalid_billing_npi_is_error():
    result = validate_claim(_claim(billing_npi="12345"))
    assert result.valid is False
    assert any("NPI" in e for e in result.errors)


def test_bad_cdt_code_is_error():
    result = validate_claim(
        _claim(lines=(ClaimLine(
            procedure_id="p1", cdt_code="X999", fee_cents=100,
            tooth_number=None, surface=None, procedure_name="bad",
        ),))
    )
    assert result.valid is False
    assert any("CDT" in e for e in result.errors)


def test_no_procedures_is_error():
    result = validate_claim(_claim(lines=()))
    assert result.valid is False
    assert any("procedure" in e.lower() for e in result.errors)


def test_pcn_over_20_chars_is_error():
    result = validate_claim(_claim(patient_control_number="X" * 21))
    assert result.valid is False
    assert any("control number" in e.lower() for e in result.errors)


def test_zero_fee_is_error():
    result = validate_claim(
        _claim(lines=(ClaimLine(
            procedure_id="p1", cdt_code="D0120", fee_cents=0,
            tooth_number=None, surface=None, procedure_name="Exam",
        ),))
    )
    assert result.valid is False
    assert any("fee" in e.lower() for e in result.errors)


def test_restorative_without_tooth_is_warning_not_error():
    result = validate_claim(
        _claim(lines=(ClaimLine(
            procedure_id="p1", cdt_code="D2740", fee_cents=90000,
            tooth_number=None, surface=None, procedure_name="Crown",
        ),))
    )
    assert result.valid is True
    assert any("tooth" in w.lower() for w in result.warnings)


def test_high_fee_is_warning():
    result = validate_claim(
        _claim(lines=(ClaimLine(
            procedure_id="p1", cdt_code="D2740", fee_cents=600000,
            tooth_number="14", surface=None, procedure_name="Crown",
        ),))
    )
    assert result.valid is True
    assert any("high" in w.lower() for w in result.warnings)
