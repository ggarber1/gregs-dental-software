"""End-to-end (in-DB, no network) flow test: a 271 response → the real parser →
the real eligibility persist (`_apply_result`) → CopayService → a co-pay estimate.

This guards the seam between Module 5 and Module 6: the per-CDT-code coinsurance
map the parser emits must be exactly what CopayService reads back. The copay-service
unit tests hand-seed `coinsurance_by_code`; THIS test proves a real parsed 271 flows
through unchanged. The live equivalent is `scripts/stedi_eligibility_smoke.py`.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.appointment_procedure import AppointmentProcedure, CdtCode
from app.models.eligibility_check import EligibilityCheck
from app.models.patient import Patient
from app.models.practice import Practice
from app.routers.eligibility import _apply_result
from app.services.copay.service import calculate_for_appointment
from app.services.eligibility.parser import parse_stedi_response

pytestmark = pytest.mark.integration

_PAYER = "62308"

# A realistic 271: active coverage, $50 deductible, $2000 annual max, and per-CDT-code
# coinsurance (A segments whose descriptions carry D-code lists) — the shape real dental
# payers return. D1110 0%, D2392 20%, D2740 50%.
_RAW_271 = {
    "payer": {"name": "CIGNA"},
    "planInformation": {"planNetworkIdDescription": "TOTAL CIGNA DPPO"},
    "planDateInformation": {"planBegin": "20260101", "planEnd": "20261231"},
    "benefitsInformation": [
        {"code": "1", "name": "Active Coverage", "serviceTypeCodes": ["35"]},
        {"code": "C", "name": "Deductible", "coverageLevelCode": "IND", "benefitAmount": "50.00"},
        {
            "code": "F", "name": "Limitations", "coverageLevelCode": "IND",
            "timeQualifierCode": "23", "benefitAmount": "2000.00",
        },
        {
            "code": "F", "name": "Limitations", "coverageLevelCode": "IND",
            "timeQualifierCode": "29", "benefitAmount": "2000.00",
        },
        {"code": "A", "benefitPercent": "0.00",
         "additionalInformation": [{"description": "D1110"}]},
        {"code": "A", "benefitPercent": "0.20",
         "additionalInformation": [{"description": "D2392"}]},
        {"code": "A", "benefitPercent": "0.50",
         "additionalInformation": [{"description": "D2740"}]},
    ],
}


@pytest_asyncio.fixture
async def flow_practice(db_session: AsyncSession) -> Practice:
    p = Practice(id=uuid.uuid4(), name="Flow Test Practice", timezone="America/New_York")
    db_session.add(p)
    await db_session.commit()
    return p


@pytest_asyncio.fixture
async def flow_patient(db_session: AsyncSession, flow_practice: Practice) -> Patient:
    pt = Patient(
        id=uuid.uuid4(), practice_id=flow_practice.id,
        first_name="Flow", last_name="Patient", date_of_birth=date(1990, 1, 1),
    )
    db_session.add(pt)
    await db_session.commit()
    return pt


@pytest_asyncio.fixture
async def flow_appointment(
    db_session: AsyncSession, flow_practice: Practice, flow_patient: Patient
) -> Appointment:
    start = datetime.now(UTC) + timedelta(days=1)
    appt = Appointment(
        id=uuid.uuid4(), practice_id=flow_practice.id, patient_id=flow_patient.id,
        start_time=start, end_time=start + timedelta(minutes=60), status="scheduled",
    )
    db_session.add(appt)
    await db_session.commit()
    return appt


async def _seed_cdt(session: AsyncSession, code: str, category: str) -> CdtCode:
    existing = await session.scalar(select(CdtCode).where(CdtCode.code == code))
    if existing:
        return existing
    c = CdtCode(id=uuid.uuid4(), code=code, description=code, category=category, is_active=True)
    session.add(c)
    await session.flush()
    return c


async def _seed_proc(
    session: AsyncSession, appt: Appointment, cdt: CdtCode, fee_cents: int
) -> AppointmentProcedure:
    p = AppointmentProcedure(
        id=uuid.uuid4(), practice_id=appt.practice_id, appointment_id=appt.id,
        patient_id=appt.patient_id, cdt_code_id=cdt.id, procedure_code=cdt.code,
        procedure_name=cdt.description, fee_cents=fee_cents,
    )
    session.add(p)
    await session.flush()
    return p


async def _persist_parsed_eligibility(
    session: AsyncSession, practice_id: uuid.UUID, patient_id: uuid.UUID
) -> EligibilityCheck:
    """Run the REAL parser + the REAL router persist helper, exactly as the
    POST /eligibility/check endpoint does — no hand-seeded coinsurance values."""
    row = EligibilityCheck(
        id=uuid.uuid4(), practice_id=practice_id, patient_id=patient_id,
        patient_insurance_id=uuid.uuid4(), idempotency_key=str(uuid.uuid4()),
        status="pending", trigger="manual", clearinghouse="stedi", payer_id_used=_PAYER,
        requested_at=datetime.now(UTC),
    )
    _apply_result(row, parse_stedi_response(_RAW_271))
    session.add(row)
    await session.flush()
    return row


def _line(calc, code: str) -> dict:
    return next(li for li in calc.line_items if li["cdtCode"] == code)


class TestEligibilityToCopayFlow:
    @pytest.mark.asyncio
    async def test_parsed_271_flows_through_to_estimate(
        self,
        db_session: AsyncSession,
        flow_practice: Practice,
        flow_patient: Patient,
        flow_appointment: Appointment,
    ) -> None:
        # 1. Parse + persist a real 271 (the parser produces coinsurance_by_code).
        check = await _persist_parsed_eligibility(
            db_session, flow_practice.id, flow_patient.id
        )
        # Sanity: the parser populated the per-code map and it was persisted.
        assert check.coinsurance_by_code == {"D1110": 0.0, "D2392": 0.2, "D2740": 0.5}
        assert check.deductible_individual == 5000
        assert check.annual_max_individual_remaining == 200000

        # 2. Seed a visit: preventive (waived, 0%), basic (20%), major (per-code 50%).
        d1110 = await _seed_cdt(db_session, "D1110", "preventive")
        d2392 = await _seed_cdt(db_session, "D2392", "basic")
        d2740 = await _seed_cdt(db_session, "D2740", "major")
        for cdt in (d1110, d2392, d2740):
            await _seed_proc(db_session, flow_appointment, cdt, fee_cents=20000)
        await db_session.commit()

        # 3. Calculate through the real service → engine.
        calc = await calculate_for_appointment(
            db_session, flow_practice.id, flow_appointment.id, user_sub="flow-test"
        )

        # 4. The parsed per-code coinsurance + deductible must drive the estimate.
        # Sort order: preventive → basic → major. $50 deductible lands on the basic line.
        prev = _line(calc, "D1110")
        assert prev["insuranceOwesCents"] == 20000 and prev["patientOwesCents"] == 0  # waived, 0%

        basic = _line(calc, "D2392")
        assert basic["deductibleAppliedCents"] == 5000
        assert basic["insuranceOwesCents"] == 12000   # (20000-5000) * 80%
        assert basic["patientOwesCents"] == 8000       # 5000 deductible + 3000 coinsurance

        major = _line(calc, "D2740")  # per-code 50% drives a 'major' line, deductible spent
        assert major["insuranceOwesCents"] == 10000 and major["patientOwesCents"] == 10000

        assert calc.total_insurance_owes_cents == 42000
        assert calc.total_patient_owes_cents == 18000
        assert calc.total_write_off_cents == 0
        # accounting identity across the visit
        assert (
            calc.total_write_off_cents
            + calc.total_patient_owes_cents
            + calc.total_insurance_owes_cents
            == calc.total_provider_fee_cents
            == 60000
        )

        # 5. Estimates written back onto the procedure rows with provenance.
        rows = (
            await db_session.scalars(
                select(AppointmentProcedure).where(
                    AppointmentProcedure.appointment_id == flow_appointment.id
                )
            )
        ).all()
        assert all(p.estimate_source == "eligibility" for p in rows)
        assert all(p.patient_est_cents is not None for p in rows)
