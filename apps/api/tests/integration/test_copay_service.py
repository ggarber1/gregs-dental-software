"""Integration tests for CopayService (calculate_for_appointment)."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.appointment_procedure import AppointmentProcedure, CdtCode
from app.models.contracted_fee_schedule import ContractedFeeSchedule
from app.models.copay_calculation import CopayCalculation
from app.models.eligibility_check import EligibilityCheck
from app.models.patient import Patient
from app.models.practice import Practice
from app.services.copay.service import CopayCalculationError, calculate_for_appointment

pytestmark = pytest.mark.integration

_PAYER = "62308"


# ── Seed helpers ────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def cs_practice(db_session: AsyncSession) -> Practice:
    p = Practice(
        id=uuid.uuid4(),
        name="CopayService Test Practice",
        timezone="America/New_York",
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest_asyncio.fixture
async def cs_patient(db_session: AsyncSession, cs_practice: Practice) -> Patient:
    pt = Patient(
        id=uuid.uuid4(),
        practice_id=cs_practice.id,
        first_name="Test",
        last_name="Patient",
        date_of_birth=date(1985, 3, 10),
    )
    db_session.add(pt)
    await db_session.commit()
    await db_session.refresh(pt)
    return pt


@pytest_asyncio.fixture
async def cs_appointment(
    db_session: AsyncSession, cs_practice: Practice, cs_patient: Patient
) -> Appointment:
    start = datetime.now(UTC) + timedelta(days=1)
    appt = Appointment(
        id=uuid.uuid4(),
        practice_id=cs_practice.id,
        patient_id=cs_patient.id,
        start_time=start,
        end_time=start + timedelta(minutes=60),
        status="scheduled",
    )
    db_session.add(appt)
    await db_session.commit()
    await db_session.refresh(appt)
    return appt


async def _seed_cdt_code(
    session: AsyncSession, code: str, category: str, description: str
) -> CdtCode:
    existing = await session.scalar(select(CdtCode).where(CdtCode.code == code))
    if existing:
        return existing
    c = CdtCode(
        id=uuid.uuid4(),
        code=code,
        description=description,
        category=category,
        is_active=True,
    )
    session.add(c)
    await session.flush()
    return c


async def _seed_procedure(
    session: AsyncSession,
    practice_id: uuid.UUID,
    appointment_id: uuid.UUID,
    patient_id: uuid.UUID,
    cdt: CdtCode,
    fee_cents: int,
) -> AppointmentProcedure:
    p = AppointmentProcedure(
        id=uuid.uuid4(),
        practice_id=practice_id,
        appointment_id=appointment_id,
        patient_id=patient_id,
        cdt_code_id=cdt.id,
        procedure_code=cdt.code,
        procedure_name=cdt.description,
        fee_cents=fee_cents,
    )
    session.add(p)
    await session.flush()
    return p


async def _seed_eligibility(
    session: AsyncSession,
    practice_id: uuid.UUID,
    patient_id: uuid.UUID,
    **overrides: object,
) -> EligibilityCheck:
    defaults: dict = {
        "id": uuid.uuid4(),
        "practice_id": practice_id,
        "patient_id": patient_id,
        "patient_insurance_id": uuid.uuid4(),
        "idempotency_key": str(uuid.uuid4()),
        "status": "verified",
        "trigger": "manual",
        "clearinghouse": "stedi",
        "payer_id_used": _PAYER,
        "plan_type": "ppo",
        "network_status": "in_network",
        "deductible_waived_preventive": True,
        "deductible_waived_diagnostic": False,
        "deductible_waived_orthodontic": False,
    }
    defaults.update(overrides)
    check = EligibilityCheck(**defaults)
    session.add(check)
    await session.flush()
    return check


async def _seed_contracted_fee(
    session: AsyncSession,
    practice_id: uuid.UUID,
    payer_id: str,
    cdt_code_id: uuid.UUID,
    allowed_amount_cents: int,
) -> ContractedFeeSchedule:
    cf = ContractedFeeSchedule(
        id=uuid.uuid4(),
        practice_id=practice_id,
        payer_id=payer_id,
        cdt_code_id=cdt_code_id,
        allowed_amount_cents=allowed_amount_cents,
        not_covered=False,
        requires_prior_auth=False,
    )
    session.add(cf)
    await session.flush()
    return cf


# ── Tests ────────────────────────────────────────────────────────────────────────


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_calculates_and_persists(
        self,
        db_session: AsyncSession,
        cs_practice: Practice,
        cs_patient: Patient,
        cs_appointment: Appointment,
    ) -> None:
        """One D2392 at $200, contracted allowed=$180, 20% coinsurance, $50 deductible unmet.

        Expected math (all integer cents):
          allowed=18000, effective=min(20000,18000)=18000, write_off=2000
          deductible_applied=5000, amount=13000
          gross_insurance=round(13000*0.80)=10400, patient_coins=2600
          patient_owes=5000+2600=7600, insurance_owes=10400
        """
        cdt = await _seed_cdt_code(
            db_session, "D2392", "basic", "Resin-based composite - two surfaces, posterior"
        )
        proc = await _seed_procedure(
            db_session,
            cs_practice.id,
            cs_appointment.id,
            cs_patient.id,
            cdt,
            fee_cents=20000,
        )
        await _seed_contracted_fee(
            db_session, cs_practice.id, _PAYER, cdt.id, allowed_amount_cents=18000
        )
        await _seed_eligibility(
            db_session,
            cs_practice.id,
            cs_patient.id,
            coinsurance_by_code={"D2392": 0.20},
            deductible_individual=5000,
            deductible_individual_met=0,
            annual_max_individual_remaining=200000,
        )
        await db_session.commit()

        result = await calculate_for_appointment(
            db_session, cs_practice.id, cs_appointment.id, user_sub="test-sub"
        )

        assert result.total_patient_owes_cents == 7600
        assert result.total_insurance_owes_cents == 10400
        assert result.plan_type == "ppo"
        assert result.appointment_id == cs_appointment.id
        assert len(result.line_items) == 1

        # Procedure row must be updated in place.
        await db_session.refresh(proc)
        assert proc.estimate_source == "eligibility"
        assert proc.patient_est_cents == 7600
        assert proc.insurance_est_cents == 10400


class TestErrorCases:
    @pytest.mark.asyncio
    async def test_no_verified_eligibility_raises(
        self,
        db_session: AsyncSession,
        cs_practice: Practice,
        cs_patient: Patient,
        cs_appointment: Appointment,
    ) -> None:
        cdt = await _seed_cdt_code(db_session, "D1110", "preventive", "Prophylaxis - adult")
        await _seed_procedure(
            db_session,
            cs_practice.id,
            cs_appointment.id,
            cs_patient.id,
            cdt,
            fee_cents=12000,
        )
        # Seed a *failed* check — should not be picked up.
        await _seed_eligibility(
            db_session,
            cs_practice.id,
            cs_patient.id,
            status="failed",
        )
        await db_session.commit()

        with pytest.raises(CopayCalculationError) as exc_info:
            await calculate_for_appointment(
                db_session, cs_practice.id, cs_appointment.id, user_sub=None
            )
        assert exc_info.value.code == "NO_ELIGIBILITY"

    @pytest.mark.asyncio
    async def test_no_procedures_raises(
        self,
        db_session: AsyncSession,
        cs_practice: Practice,
        cs_patient: Patient,
        cs_appointment: Appointment,
    ) -> None:
        await _seed_eligibility(db_session, cs_practice.id, cs_patient.id)
        await db_session.commit()

        with pytest.raises(CopayCalculationError) as exc_info:
            await calculate_for_appointment(
                db_session, cs_practice.id, cs_appointment.id, user_sub=None
            )
        assert exc_info.value.code == "NO_PROCEDURES"


    @pytest.mark.asyncio
    async def test_missing_appointment_raises(
        self, db_session: AsyncSession, cs_practice: Practice
    ) -> None:
        with pytest.raises(CopayCalculationError) as exc_info:
            await calculate_for_appointment(
                db_session, cs_practice.id, uuid.uuid4(), user_sub=None
            )
        assert exc_info.value.code == "APPOINTMENT_NOT_FOUND"


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_second_call_updates_in_place(
        self,
        db_session: AsyncSession,
        cs_practice: Practice,
        cs_patient: Patient,
        cs_appointment: Appointment,
    ) -> None:
        cdt = await _seed_cdt_code(db_session, "D0120", "diagnostic", "Periodic oral evaluation")
        await _seed_procedure(
            db_session,
            cs_practice.id,
            cs_appointment.id,
            cs_patient.id,
            cdt,
            fee_cents=8000,
        )
        await _seed_eligibility(
            db_session,
            cs_practice.id,
            cs_patient.id,
            coinsurance_basic=0.20,
            deductible_individual=0,
            deductible_individual_met=0,
            annual_max_individual_remaining=150000,
        )
        await db_session.commit()

        first = await calculate_for_appointment(
            db_session, cs_practice.id, cs_appointment.id, user_sub="sub-a"
        )
        second = await calculate_for_appointment(
            db_session, cs_practice.id, cs_appointment.id, user_sub="sub-b"
        )

        assert first.id == second.id

        # Only one row should exist.
        count = len(
            (
                await db_session.scalars(
                    select(CopayCalculation).where(
                        CopayCalculation.appointment_id == cs_appointment.id
                    )
                )
            ).all()
        )
        assert count == 1
