from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.services.claims.builder import build_claim_input


@dataclass
class _Practice:
    name: str = "Downtown Dental"
    billing_npi: str | None = "1234567890"
    billing_taxonomy_code: str | None = "1223G0001X"
    clearinghouse_submitter_id: str | None = "SUB1"
    address_line1: str | None = "1 Main St"
    city: str | None = "Boston"
    state: str | None = "MA"
    zip: str | None = "02101-1234"


@dataclass
class _Provider:
    npi: str = "1234567890"
    # Real Provider model uses full_name, not first_name/last_name
    full_name: str = "Jane Dentist"


@dataclass
class _Patient:
    first_name: str = "John"
    last_name: str = "Smith"
    date_of_birth: date = date(1980, 1, 1)
    sex: str | None = "male"
    address_line1: str | None = "2 Oak Ave"
    city: str | None = "Boston"
    state: str | None = "MA"
    zip: str | None = "02102"


@dataclass
class _Insurance:
    relationship_to_insured: str = "self"
    member_id: str | None = "U123"
    group_number: str | None = "GRP1"
    insured_first_name: str | None = None
    insured_last_name: str | None = None
    insured_date_of_birth: date | None = None


@dataclass
class _Proc:
    id: str
    procedure_code: str
    procedure_name: str
    fee_cents: int
    tooth_number: str | None = None
    surface: str | None = None


@dataclass
class _Appt:
    start_time: datetime = datetime(2026, 6, 18, 14, 0, tzinfo=UTC)


def test_builds_self_subscriber_and_sums_charges():
    claim = build_claim_input(
        appt=_Appt(),
        procedures=[
            _Proc("p1", "D2392", "Resin", 20000, "14", "O"),
            _Proc("p2", "D0120", "Exam", 5000),
        ],
        patient=_Patient(),
        insurance=_Insurance(),
        payer_id="CDLA1",
        practice=_Practice(),
        provider=_Provider(),
        billing_tax_id="123456789",
        pcn="ABC123",
        usage_indicator="T",
    )
    assert claim.total_charge_cents == 25000
    assert claim.subscriber_first_name == "John"   # self -> patient identity
    assert claim.relationship_to_insured == "self"
    assert len(claim.lines) == 2
    assert claim.lines[0].procedure_id == "p1"
    assert claim.lines[0].cdt_code == "D2392"
    assert claim.date_of_service == date(2026, 6, 18)
    assert claim.billing_address.city == "Boston"
    assert claim.subscriber_gender == "M"


def test_non_self_uses_insured_identity_for_subscriber():
    claim = build_claim_input(
        appt=_Appt(),
        procedures=[_Proc("p1", "D0120", "Exam", 5000)],
        patient=_Patient(),
        insurance=_Insurance(
            relationship_to_insured="child",
            insured_first_name="Mary",
            insured_last_name="Smith",
            insured_date_of_birth=date(1975, 3, 3),
        ),
        payer_id="CDLA1",
        practice=_Practice(),
        provider=_Provider(),
        billing_tax_id="123456789",
        pcn="ABC123",
        usage_indicator="T",
    )
    assert claim.subscriber_first_name == "Mary"
    assert claim.subscriber_dob == date(1975, 3, 3)
    assert claim.patient_first_name == "John"     # patient stays the patient
    assert claim.relationship_to_insured == "child"
