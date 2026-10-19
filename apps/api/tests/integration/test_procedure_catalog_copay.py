"""A procedure created through the API with only a code must reach the co-pay engine
linked to its catalog row — so the engine sees its category and contracted fee.

Regression for staging 2026-10-19: UI-created procedures had cdt_code_id = NULL, so
contracted fees were never matched and every line was treated as category "other".
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.appointment_procedure import CdtCode
from app.models.contracted_fee_schedule import ContractedFeeSchedule
from app.models.patient import Patient
from app.services.copay.service import calculate_for_appointment
from tests.integration.conftest import mut
from tests.integration.test_eligibility_to_copay_flow import _PAYER, _persist_parsed_eligibility

pytestmark = pytest.mark.integration


async def test_code_only_procedure_uses_category_and_contracted_fee(
    client: AsyncClient, auth_headers, db_session: AsyncSession, practice
) -> None:
    patient = Patient(
        id=uuid.uuid4(),
        practice_id=practice.id,
        first_name="Catalog",
        last_name="Link",
        date_of_birth=date(1990, 1, 1),
    )
    start = datetime.now(UTC) + timedelta(days=1)
    appt = Appointment(
        id=uuid.uuid4(),
        practice_id=practice.id,
        patient_id=patient.id,
        start_time=start,
        end_time=start + timedelta(minutes=30),
        status="scheduled",
    )
    db_session.add_all([patient, appt])
    await db_session.flush()

    d1110 = await db_session.scalar(select(CdtCode).where(CdtCode.code == "D1110"))
    assert d1110 is not None
    db_session.add(
        ContractedFeeSchedule(
            id=uuid.uuid4(),
            practice_id=practice.id,
            payer_id=_PAYER,
            cdt_code_id=d1110.id,
            allowed_amount_cents=9000,
        )
    )
    await _persist_parsed_eligibility(db_session, practice.id, patient.id)
    await db_session.commit()

    created = await client.post(
        f"/api/v1/appointments/{appt.id}/procedures",
        json={"procedureCode": "D1110", "procedureName": "Prophy", "feeCents": 12000},
        headers=mut(auth_headers),
    )
    assert created.status_code == 201, created.text

    calc = await calculate_for_appointment(db_session, practice.id, appt.id, user_sub="t")

    line = next(li for li in calc.line_items if li["cdtCode"] == "D1110")
    assert line["category"] == d1110.category
    assert line["allowedAmountCents"] == 9000
    assert calc.total_write_off_cents == 3000
