from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import mut


@pytest_asyncio.fixture
async def proc_patient(db_session: AsyncSession, practice):
    from app.models.patient import Patient

    p = Patient(
        id=uuid.uuid4(),
        practice_id=practice.id,
        first_name="Proc",
        last_name="Testpatient",
        date_of_birth=date(1990, 1, 1),
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest_asyncio.fixture
async def proc_appointment(db_session: AsyncSession, practice, proc_patient):
    from app.models.appointment import Appointment

    start = datetime.now(UTC) + timedelta(days=1)
    appt = Appointment(
        id=uuid.uuid4(),
        practice_id=practice.id,
        patient_id=proc_patient.id,
        start_time=start,
        end_time=start + timedelta(minutes=30),
        status="scheduled",
    )
    db_session.add(appt)
    await db_session.commit()
    await db_session.refresh(appt)
    return appt


# ── Sub-task A: CDT typeahead ──────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cdt_search_by_code_prefix(client: AsyncClient, auth_headers):
    resp = await client.get("/api/v1/cdt-codes?q=D11", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert "D1110" in [r["code"] for r in resp.json()]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cdt_search_by_description(client: AsyncClient, auth_headers):
    resp = await client.get("/api/v1/cdt-codes?q=prophylaxis", headers=auth_headers)
    assert resp.status_code == 200
    assert "D1110" in [r["code"] for r in resp.json()]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cdt_search_empty_returns_list(client: AsyncClient, auth_headers):
    resp = await client.get("/api/v1/cdt-codes", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


# ── Sub-task B: list + totals ──────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_empty_then_totals_zero(client, auth_headers, proc_appointment):
    url = f"/api/v1/appointments/{proc_appointment.id}/procedures"
    resp = await client.get(url, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []
    assert resp.json()["totals"] == {
        "feeCentsTotal": 0,
        "insuranceEstCentsTotal": 0,
        "patientEstCentsTotal": 0,
    }


# ── Sub-task C: create ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_then_totals_recompute(client, auth_headers, proc_appointment):
    url = f"/api/v1/appointments/{proc_appointment.id}/procedures"
    for payload in (
        {
            "procedureCode": "D1110",
            "procedureName": "Prophy",
            "feeCents": 12000,
            "insuranceEstCents": 9600,
            "patientEstCents": 2400,
            "estimateSource": "manual",
        },
        {"procedureCode": "D0120", "procedureName": "Periodic exam", "feeCents": 5000},
        {
            "procedureCode": "D0274",
            "procedureName": "Bitewings",
            "feeCents": 6500,
            "insuranceEstCents": 6500,
            "patientEstCents": 0,
            "estimateSource": "eligibility",
        },
    ):
        r = await client.post(url, json=payload, headers=mut(auth_headers))
        assert r.status_code == 201, r.text
    body = (await client.get(url, headers=auth_headers)).json()
    assert len(body["items"]) == 3
    assert body["totals"]["feeCentsTotal"] == 23500
    assert body["totals"]["insuranceEstCentsTotal"] == 16100
    assert body["totals"]["patientEstCentsTotal"] == 2400


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_requires_code_or_name(client, auth_headers, proc_appointment):
    url = f"/api/v1/appointments/{proc_appointment.id}/procedures"
    r = await client.post(
        url, json={"procedureName": "Mystery", "feeCents": 1000}, headers=mut(auth_headers)
    )
    assert r.status_code == 422


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_404_missing_appointment(client, auth_headers):
    url = f"/api/v1/appointments/{uuid.uuid4()}/procedures"
    r = await client.post(
        url,
        json={"procedureCode": "D1110", "procedureName": "Prophy", "feeCents": 1000},
        headers=mut(auth_headers),
    )
    assert r.status_code == 404


# ── Sub-task D: edit + soft-delete ─────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.integration
async def test_patch_updates_fields(client, auth_headers, proc_appointment):
    url = f"/api/v1/appointments/{proc_appointment.id}/procedures"
    created = await client.post(
        url,
        json={"procedureCode": "D2391", "procedureName": "Composite", "feeCents": 20000},
        headers=mut(auth_headers),
    )
    pid = created.json()["id"]
    r = await client.patch(
        f"{url}/{pid}",
        json={
            "feeCents": 18000,
            "insuranceEstCents": 14400,
            "patientEstCents": 3600,
            "estimateSource": "manual",
            "toothNumber": "14",
        },
        headers=mut(auth_headers),
    )
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["feeCents"] == 18000 and b["toothNumber"] == "14" and b["patientEstCents"] == 3600


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delete_soft_deletes_and_recomputes(client, auth_headers, proc_appointment):
    url = f"/api/v1/appointments/{proc_appointment.id}/procedures"
    a = await client.post(
        url,
        json={"procedureCode": "D1110", "procedureName": "Prophy", "feeCents": 12000},
        headers=mut(auth_headers),
    )
    await client.post(
        url,
        json={"procedureCode": "D0120", "procedureName": "Exam", "feeCents": 5000},
        headers=mut(auth_headers),
    )
    del_id = a.json()["id"]
    r = await client.delete(f"{url}/{del_id}", headers=mut(auth_headers))
    assert r.status_code == 204
    listing = (await client.get(url, headers=auth_headers)).json()
    assert del_id not in [row["id"] for row in listing["items"]]
    assert listing["totals"]["feeCentsTotal"] == 5000


@pytest.mark.asyncio
@pytest.mark.integration
async def test_patch_404_wrong_id(client, auth_headers, proc_appointment):
    url = f"/api/v1/appointments/{proc_appointment.id}/procedures"
    r = await client.patch(
        f"{url}/{uuid.uuid4()}", json={"feeCents": 1}, headers=mut(auth_headers)
    )
    assert r.status_code == 404


# ── Sub-task E: cross-practice authz + appointment-delete cascade ──────────────


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cannot_touch_other_practice_appointment(client, auth_headers, db_session):
    from app.models.appointment import Appointment
    from app.models.patient import Patient
    from app.models.practice import Practice

    other = Practice(id=uuid.uuid4(), name="Rival Dental", timezone="UTC")
    db_session.add(other)
    await db_session.flush()
    op = Patient(
        id=uuid.uuid4(),
        practice_id=other.id,
        first_name="Other",
        last_name="Pt",
        date_of_birth=date(1980, 2, 2),
    )
    db_session.add(op)
    await db_session.flush()
    start = datetime.now(UTC) + timedelta(days=2)
    appt = Appointment(
        id=uuid.uuid4(),
        practice_id=other.id,
        patient_id=op.id,
        start_time=start,
        end_time=start + timedelta(minutes=30),
        status="scheduled",
    )
    db_session.add(appt)
    await db_session.commit()
    # auth_headers is scoped to the first `practice`, not `other`.
    url = f"/api/v1/appointments/{appt.id}/procedures"
    r = await client.post(
        url,
        json={"procedureCode": "D1110", "procedureName": "Prophy", "feeCents": 1000},
        headers=mut(auth_headers),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
@pytest.mark.integration
async def test_deleting_appointment_cascades_procedures(
    client, auth_headers, proc_appointment, db_session
):
    from sqlalchemy import delete as sa_delete
    from sqlalchemy import func as sa_func
    from sqlalchemy import select as sa_select

    from app.models.appointment import Appointment
    from app.models.appointment_procedure import AppointmentProcedure

    url = f"/api/v1/appointments/{proc_appointment.id}/procedures"
    await client.post(
        url,
        json={"procedureCode": "D1110", "procedureName": "Prophy", "feeCents": 12000},
        headers=mut(auth_headers),
    )
    # Confirm the procedure is visible from db_session (shared engine) before delete.
    before = await db_session.scalar(
        sa_select(sa_func.count())
        .select_from(AppointmentProcedure)
        .where(AppointmentProcedure.appointment_id == proc_appointment.id)
    )
    assert before == 1, "API-committed procedure should be visible to db_session"

    await db_session.execute(
        sa_delete(Appointment).where(Appointment.id == proc_appointment.id)
    )
    await db_session.commit()

    remaining = await db_session.scalar(
        sa_select(sa_func.count())
        .select_from(AppointmentProcedure)
        .where(AppointmentProcedure.appointment_id == proc_appointment.id)
    )
    assert remaining == 0
