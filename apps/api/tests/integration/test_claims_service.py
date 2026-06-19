import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt
from app.models.appointment import Appointment
from app.models.appointment_procedure import AppointmentProcedure
from app.models.insurance_plan import InsurancePlan
from app.models.patient import Patient
from app.models.patient_insurance import PatientInsurance
from app.models.practice import Practice
from app.models.provider import Provider
from app.services.claims.base import (
    ClaimResult,
    ClaimSubmissionError,
    ClearinghouseClient,
    DentalClaimInput,
)
from app.services.claims.service import (
    ClaimSubmissionPrereqError,
    submit_claim_for_appointment,
)

pytestmark = pytest.mark.integration


class _FakeClient(ClearinghouseClient):
    def __init__(self, result: ClaimResult):
        self._result = result
        self.calls = 0

    async def submit_dental_claim(
        self, claim: DentalClaimInput, idempotency_key: str
    ) -> ClaimResult:
        self.calls += 1
        return self._result


def _ok_result() -> ClaimResult:
    return ClaimResult(
        accepted=True, clearinghouse_claim_id="txn-1", clearinghouse_status="ACCEPTED",
        errors=[], raw_request={"k": "v"}, raw_response={"transactionId": "txn-1"},
    )


async def _seed(session: AsyncSession):
    practice = Practice(
        id=uuid.uuid4(), name="Downtown Dental",
        features={"claims_submission": True},
        billing_npi="1234567890", billing_taxonomy_code="1223G0001X",
        billing_tax_id_encrypted=encrypt("123456789"),
        clearinghouse_submitter_id="SUB1", clearinghouse_provider="stedi",
        clearinghouse_api_key_ssm_path="/dental/staging/clearinghouse/api_key",
    )
    session.add(practice)
    provider = Provider(
        id=uuid.uuid4(), practice_id=practice.id, npi="1234567890",
        full_name="Jane Dentist", provider_type="dentist",
    )
    patient = Patient(
        id=uuid.uuid4(), practice_id=practice.id, first_name="John", last_name="Smith",
        date_of_birth=date(1980, 1, 1),
    )
    # InsurancePlan uses carrier_name (not name) per the model definition
    plan = InsurancePlan(
        id=uuid.uuid4(), practice_id=practice.id, payer_id="CDLA1", carrier_name="Cigna DPPO",
    )
    session.add_all([provider, patient, plan])
    insurance = PatientInsurance(
        id=uuid.uuid4(), practice_id=practice.id, patient_id=patient.id, priority="primary",
        carrier="Cigna", member_id="U123", group_number="GRP1",
        relationship_to_insured="self", insurance_plan_id=plan.id,
    )
    appt = Appointment(
        id=uuid.uuid4(), practice_id=practice.id, patient_id=patient.id,
        provider_id=provider.id, start_time=datetime(2026, 6, 18, 14, 0, tzinfo=UTC),
        end_time=datetime(2026, 6, 18, 15, 0, tzinfo=UTC),
    )
    session.add_all([insurance, appt])
    # Flush appointment before procedure: the DB has an explicit FK on appointment_id
    # that the ORM model doesn't declare, so SQLAlchemy can't sort the INSERTs.
    await session.flush()
    proc = AppointmentProcedure(
        id=uuid.uuid4(), practice_id=practice.id, appointment_id=appt.id, patient_id=patient.id,
        procedure_code="D2392", procedure_name="Resin", fee_cents=20000, tooth_number="14",
    )
    session.add(proc)
    await session.commit()
    return practice, appt


@pytest.mark.asyncio
async def test_submits_and_persists_submitted(db_session: AsyncSession):
    practice, appt = await _seed(db_session)
    client = _FakeClient(_ok_result())
    claim = await submit_claim_for_appointment(
        db_session, practice.id, appt.id, "idem-1",
        client=client, usage_indicator="T", user_sub="sub-1",
    )
    assert claim.status == "submitted"
    assert claim.clearinghouse_claim_id == "txn-1"
    assert claim.total_charge_cents == 20000
    assert client.calls == 1


@pytest.mark.asyncio
async def test_idempotent_second_call_returns_same_row(db_session: AsyncSession):
    practice, appt = await _seed(db_session)
    client = _FakeClient(_ok_result())
    first = await submit_claim_for_appointment(
        db_session, practice.id, appt.id, "idem-1",
        client=client, usage_indicator="T", user_sub="sub-1",
    )
    second = await submit_claim_for_appointment(
        db_session, practice.id, appt.id, "idem-1",
        client=client, usage_indicator="T", user_sub="sub-1",
    )
    assert first.id == second.id
    assert client.calls == 1


@pytest.mark.asyncio
async def test_rejected_result_marks_clearinghouse_rejected(db_session: AsyncSession):
    practice, appt = await _seed(db_session)
    rejected = ClaimResult(
        accepted=False, clearinghouse_claim_id="txn-x", clearinghouse_status="REJECTED",
        errors=["Invalid member ID"], raw_request={}, raw_response={},
    )
    claim = await submit_claim_for_appointment(
        db_session, practice.id, appt.id, "idem-2", client=_FakeClient(rejected),
        usage_indicator="T", user_sub="sub-1",
    )
    assert claim.status == "clearinghouse_rejected"
    assert claim.submission_errors == ["Invalid member ID"]


@pytest.mark.asyncio
async def test_no_procedures_raises_prereq_error(db_session: AsyncSession):
    practice, appt = await _seed(db_session)
    proc = await db_session.scalar(
        select(AppointmentProcedure).where(AppointmentProcedure.appointment_id == appt.id)
    )
    await db_session.delete(proc)
    await db_session.commit()
    with pytest.raises(ClaimSubmissionPrereqError) as exc:
        await submit_claim_for_appointment(
            db_session, practice.id, appt.id, "idem-3", client=_FakeClient(_ok_result()),
            usage_indicator="T", user_sub="sub-1",
        )
    assert exc.value.code == "NO_PROCEDURES"


class _RaisingClient(ClearinghouseClient):
    async def submit_dental_claim(self, claim, idempotency_key):
        raise ClaimSubmissionError("Stedi timeout", retryable=True)


@pytest.mark.asyncio
async def test_transport_error_marks_submission_failed(db_session: AsyncSession):
    practice, appt = await _seed(db_session)
    claim = await submit_claim_for_appointment(
        db_session, practice.id, appt.id, "idem-5", client=_RaisingClient(),
        usage_indicator="T", user_sub="sub-1",
    )
    assert claim.status == "submission_failed"
    assert claim.submission_errors and "timeout" in claim.submission_errors[0].lower()
