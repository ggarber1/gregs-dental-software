"""
Integration tests for the scheduling module.

Requires a running Postgres at localhost:5432 and Redis at localhost:6379.
Run with: pytest -m integration tests/integration/test_scheduling.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from tests.integration.conftest import mut

# ── Practice Endpoint ────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_get_practice_returns_timezone(client, auth_headers):
    """GET /api/v1/practice returns the practice's timezone."""
    resp = await client.get("/api/v1/practice", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["timezone"] == "America/New_York"
    assert body["name"] == "Sunrise Dental"
    assert "id" in body
    assert "createdAt" in body
    assert "updatedAt" in body


# ── Appointment Types CRUD ────────────────────────────────────────────────────


@pytest.mark.integration
async def test_appointment_type_crud(client, auth_headers):
    h = auth_headers

    # Create
    resp = await client.post(
        "/api/v1/appointment-types",
        json={
            "name": "New Patient Exam",
            "durationMinutes": 60,
            "color": "#FF5733",
            "defaultCdtCodes": ["D0150", "D0210"],
        },
        headers=mut(h),
    )
    assert resp.status_code == 201
    at = resp.json()
    at_id = at["id"]
    assert at["name"] == "New Patient Exam"
    assert at["durationMinutes"] == 60
    assert at["defaultCdtCodes"] == ["D0150", "D0210"]

    # List
    resp = await client.get("/api/v1/appointment-types", headers=h)
    assert resp.status_code == 200
    types = resp.json()
    assert any(t["id"] == at_id for t in types)

    # Get
    resp = await client.get(f"/api/v1/appointment-types/{at_id}", headers=h)
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Patient Exam"

    # Update
    resp = await client.patch(
        f"/api/v1/appointment-types/{at_id}",
        json={"name": "Comprehensive Exam", "durationMinutes": 90},
        headers=mut(h),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Comprehensive Exam"
    assert resp.json()["durationMinutes"] == 90

    # Delete (soft)
    resp = await client.delete(f"/api/v1/appointment-types/{at_id}", headers=mut(h))
    assert resp.status_code == 204

    # Verify deleted — GET returns 404
    resp = await client.get(f"/api/v1/appointment-types/{at_id}", headers=h)
    assert resp.status_code == 404


# ── Providers CRUD ────────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_provider_crud(client, auth_headers):
    h = auth_headers

    # Create
    resp = await client.post(
        "/api/v1/providers",
        json={
            "fullName": "Dr. Johnson",
            "npi": "9876543210",
            "providerType": "dentist",
            "licenseNumber": "DDS-99999",
            "specialty": "Endodontics",
        },
        headers=mut(h),
    )
    assert resp.status_code == 201
    prov = resp.json()
    prov_id = prov["id"]
    assert prov["fullName"] == "Dr. Johnson"
    assert prov["npi"] == "9876543210"

    # List
    resp = await client.get("/api/v1/providers", headers=h)
    assert resp.status_code == 200
    assert any(p["id"] == prov_id for p in resp.json())

    # Get
    resp = await client.get(f"/api/v1/providers/{prov_id}", headers=h)
    assert resp.status_code == 200

    # Update
    resp = await client.patch(
        f"/api/v1/providers/{prov_id}",
        json={"fullName": "Dr. Johnson II"},
        headers=mut(h),
    )
    assert resp.status_code == 200
    assert resp.json()["fullName"] == "Dr. Johnson II"

    # Delete (soft)
    resp = await client.delete(f"/api/v1/providers/{prov_id}", headers=mut(h))
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/providers/{prov_id}", headers=h)
    assert resp.status_code == 404


# ── Operatories CRUD ──────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_operatory_crud(client, auth_headers):
    h = auth_headers

    # Create
    resp = await client.post(
        "/api/v1/operatories",
        json={"name": "Room B", "color": "#AABBCC"},
        headers=mut(h),
    )
    assert resp.status_code == 201
    op = resp.json()
    op_id = op["id"]
    assert op["name"] == "Room B"

    # List
    resp = await client.get("/api/v1/operatories", headers=h)
    assert resp.status_code == 200
    assert any(o["id"] == op_id for o in resp.json())

    # Update
    resp = await client.patch(
        f"/api/v1/operatories/{op_id}",
        json={"name": "Room B (updated)"},
        headers=mut(h),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Room B (updated)"

    # Delete (soft)
    resp = await client.delete(f"/api/v1/operatories/{op_id}", headers=mut(h))
    assert resp.status_code == 204


# ── Appointment Lifecycle ─────────────────────────────────────────────────────


@pytest.mark.integration
async def test_appointment_full_lifecycle(
    client, auth_headers, patient, provider, operatory, appointment_type
):
    """Create -> confirm -> check_in -> in_chair -> completed."""
    h = auth_headers

    start = datetime(2026, 7, 1, 14, 0, tzinfo=UTC)
    end = start + timedelta(minutes=45)

    # Create appointment
    resp = await client.post(
        "/api/v1/appointments",
        json={
            "patientId": str(patient.id),
            "providerId": str(provider.id),
            "operatoryId": str(operatory.id),
            "appointmentTypeId": str(appointment_type.id),
            "startTime": start.isoformat(),
            "endTime": end.isoformat(),
            "notes": "First visit",
        },
        headers=mut(h),
    )
    assert resp.status_code == 201
    appt = resp.json()
    appt_id = appt["id"]
    assert appt["status"] == "scheduled"
    assert appt["patientName"] == f"{patient.first_name} {patient.last_name}"
    assert appt["providerName"] == provider.full_name
    assert appt["operatoryName"] == operatory.name
    assert appt["appointmentTypeName"] == appointment_type.name

    # Confirm
    resp = await client.patch(
        f"/api/v1/appointments/{appt_id}",
        json={"status": "confirmed"},
        headers=mut(h),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"

    # Check in
    resp = await client.patch(
        f"/api/v1/appointments/{appt_id}",
        json={"status": "checked_in"},
        headers=mut(h),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "checked_in"

    # In chair
    resp = await client.patch(
        f"/api/v1/appointments/{appt_id}",
        json={"status": "in_chair"},
        headers=mut(h),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_chair"

    # Complete
    resp = await client.patch(
        f"/api/v1/appointments/{appt_id}",
        json={"status": "completed"},
        headers=mut(h),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.integration
async def test_appointment_invalid_status_transition(
    client, auth_headers, patient, provider, operatory
):
    """Completed appointment cannot go back to scheduled."""
    h = auth_headers

    start = datetime(2026, 7, 2, 10, 0, tzinfo=UTC)
    end = start + timedelta(minutes=30)

    # Create and advance to completed
    resp = await client.post(
        "/api/v1/appointments",
        json={
            "patientId": str(patient.id),
            "providerId": str(provider.id),
            "operatoryId": str(operatory.id),
            "startTime": start.isoformat(),
            "endTime": end.isoformat(),
        },
        headers=mut(h),
    )
    appt_id = resp.json()["id"]

    for status in ["confirmed", "checked_in", "in_chair", "completed"]:
        resp = await client.patch(
            f"/api/v1/appointments/{appt_id}",
            json={"status": status},
            headers=mut(h),
        )
        assert resp.status_code == 200

    # Now try going back — should fail
    resp = await client.patch(
        f"/api/v1/appointments/{appt_id}",
        json={"status": "scheduled"},
        headers=mut(h),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


# ── Double-Booking Detection ─────────────────────────────────────────────────


@pytest.mark.integration
async def test_double_booking_same_provider_rejected(
    client, auth_headers, patient, provider, operatory, db_session
):
    """Two appointments for the same provider at overlapping times should be rejected."""
    h = auth_headers

    # Create a second operatory so only the provider conflicts
    from app.models.operatory import Operatory

    op2 = Operatory(
        id=uuid.uuid4(),
        practice_id=operatory.practice_id,
        name="Operatory 2",
        color="#AABB11",
    )
    db_session.add(op2)
    await db_session.commit()
    await db_session.refresh(op2)

    start = datetime(2026, 7, 3, 9, 0, tzinfo=UTC)
    end = start + timedelta(minutes=60)

    # First appointment — should succeed
    resp = await client.post(
        "/api/v1/appointments",
        json={
            "patientId": str(patient.id),
            "providerId": str(provider.id),
            "operatoryId": str(operatory.id),
            "startTime": start.isoformat(),
            "endTime": end.isoformat(),
        },
        headers=mut(h),
    )
    assert resp.status_code == 201

    # Second appointment — same provider, overlapping time, different operatory -> 409
    overlap_start = start + timedelta(minutes=30)
    overlap_end = end + timedelta(minutes=30)

    resp = await client.post(
        "/api/v1/appointments",
        json={
            "patientId": str(patient.id),
            "providerId": str(provider.id),
            "operatoryId": str(op2.id),
            "startTime": overlap_start.isoformat(),
            "endTime": overlap_end.isoformat(),
        },
        headers=mut(h),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "SCHEDULING_CONFLICT"
    conflicts = resp.json()["error"]["details"]["conflicts"]
    assert any(c["type"] == "provider" for c in conflicts)


@pytest.mark.integration
async def test_double_booking_same_operatory_rejected(
    client, auth_headers, patient, provider, operatory, db_session
):
    """Two appointments in the same operatory at overlapping times should be rejected."""
    h = auth_headers

    # Create a second provider so only the operatory conflicts
    from app.models.provider import Provider

    prov2 = Provider(
        id=uuid.uuid4(),
        practice_id=provider.practice_id,
        full_name="Dr. Jones",
        npi="5555555555",
        provider_type="hygienist",
    )
    db_session.add(prov2)
    await db_session.commit()
    await db_session.refresh(prov2)

    start = datetime(2026, 7, 4, 11, 0, tzinfo=UTC)
    end = start + timedelta(minutes=45)

    # First
    resp = await client.post(
        "/api/v1/appointments",
        json={
            "patientId": str(patient.id),
            "providerId": str(provider.id),
            "operatoryId": str(operatory.id),
            "startTime": start.isoformat(),
            "endTime": end.isoformat(),
        },
        headers=mut(h),
    )
    assert resp.status_code == 201

    # Second — different provider, same operatory, overlapping -> 409
    resp = await client.post(
        "/api/v1/appointments",
        json={
            "patientId": str(patient.id),
            "providerId": str(prov2.id),
            "operatoryId": str(operatory.id),
            "startTime": (start + timedelta(minutes=15)).isoformat(),
            "endTime": (end + timedelta(minutes=15)).isoformat(),
        },
        headers=mut(h),
    )
    assert resp.status_code == 409
    assert any(
        c["type"] == "operatory" for c in resp.json()["error"]["details"]["conflicts"]
    )


@pytest.mark.integration
async def test_cancelled_appointment_does_not_block_booking(
    client, auth_headers, patient, provider, operatory
):
    """A cancelled appointment should not cause a conflict."""
    h = auth_headers

    start = datetime(2026, 7, 5, 13, 0, tzinfo=UTC)
    end = start + timedelta(minutes=30)

    # Book then cancel
    resp = await client.post(
        "/api/v1/appointments",
        json={
            "patientId": str(patient.id),
            "providerId": str(provider.id),
            "operatoryId": str(operatory.id),
            "startTime": start.isoformat(),
            "endTime": end.isoformat(),
        },
        headers=mut(h),
    )
    appt_id = resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/appointments/{appt_id}",
        headers=mut(h),
    )
    assert resp.status_code == 204

    # Book again at the same time — should succeed
    resp = await client.post(
        "/api/v1/appointments",
        json={
            "patientId": str(patient.id),
            "providerId": str(provider.id),
            "operatoryId": str(operatory.id),
            "startTime": start.isoformat(),
            "endTime": end.isoformat(),
        },
        headers=mut(h),
    )
    assert resp.status_code == 201


# ── Cancel with Reason ────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_cancel_appointment_with_reason(
    client, auth_headers, patient, provider, operatory
):
    h = auth_headers

    start = datetime(2026, 7, 6, 8, 0, tzinfo=UTC)
    end = start + timedelta(minutes=30)

    resp = await client.post(
        "/api/v1/appointments",
        json={
            "patientId": str(patient.id),
            "providerId": str(provider.id),
            "operatoryId": str(operatory.id),
            "startTime": start.isoformat(),
            "endTime": end.isoformat(),
        },
        headers=mut(h),
    )
    appt_id = resp.json()["id"]

    resp = await client.request(
        "DELETE",
        f"/api/v1/appointments/{appt_id}",
        json={"cancellationReason": "Patient requested reschedule"},
        headers=mut(h),
    )
    assert resp.status_code == 204


@pytest.mark.integration
async def test_cancel_completed_appointment_returns_422(
    client, auth_headers, patient, provider, operatory
):
    h = auth_headers

    start = datetime(2026, 7, 7, 15, 0, tzinfo=UTC)
    end = start + timedelta(minutes=30)

    resp = await client.post(
        "/api/v1/appointments",
        json={
            "patientId": str(patient.id),
            "providerId": str(provider.id),
            "operatoryId": str(operatory.id),
            "startTime": start.isoformat(),
            "endTime": end.isoformat(),
        },
        headers=mut(h),
    )
    appt_id = resp.json()["id"]

    # Advance to completed
    for status in ["confirmed", "checked_in", "in_chair", "completed"]:
        await client.patch(
            f"/api/v1/appointments/{appt_id}",
            json={"status": status},
            headers=mut(h),
        )

    # Try to cancel — should fail
    resp = await client.delete(f"/api/v1/appointments/{appt_id}", headers=mut(h))
    assert resp.status_code == 422


# ── List / Filter ─────────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_list_appointments_returns_all(
    client, auth_headers, patient, provider, operatory
):
    h = auth_headers

    # Create 3 appointments on different days
    for day_offset in range(3):
        start = datetime(2026, 8, 1 + day_offset, 10, 0, tzinfo=UTC)
        end = start + timedelta(minutes=30)
        resp = await client.post(
            "/api/v1/appointments",
            json={
                "patientId": str(patient.id),
                "providerId": str(provider.id),
                "operatoryId": str(operatory.id),
                "startTime": start.isoformat(),
                "endTime": end.isoformat(),
            },
            headers=mut(h),
        )
        assert resp.status_code == 201

    # List all — should get at least 3
    resp = await client.get("/api/v1/appointments", headers=h)
    assert resp.status_code == 200
    appts = resp.json()
    assert len(appts) >= 3


# ── Reschedule with Conflict Re-Check ────────────────────────────────────────


@pytest.mark.integration
async def test_reschedule_into_conflict_rejected(
    client, auth_headers, patient, provider, operatory
):
    """Moving an appointment to overlap with another should be rejected."""
    h = auth_headers

    start1 = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)
    end1 = start1 + timedelta(minutes=60)
    start2 = datetime(2026, 8, 10, 11, 0, tzinfo=UTC)
    end2 = start2 + timedelta(minutes=60)

    # Create two non-overlapping appointments
    resp1 = await client.post(
        "/api/v1/appointments",
        json={
            "patientId": str(patient.id),
            "providerId": str(provider.id),
            "operatoryId": str(operatory.id),
            "startTime": start1.isoformat(),
            "endTime": end1.isoformat(),
        },
        headers=mut(h),
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        "/api/v1/appointments",
        json={
            "patientId": str(patient.id),
            "providerId": str(provider.id),
            "operatoryId": str(operatory.id),
            "startTime": start2.isoformat(),
            "endTime": end2.isoformat(),
        },
        headers=mut(h),
    )
    assert resp2.status_code == 201
    appt2_id = resp2.json()["id"]

    # Reschedule appt2 to overlap with appt1 -> 409
    resp = await client.patch(
        f"/api/v1/appointments/{appt2_id}",
        json={
            "startTime": (start1 + timedelta(minutes=30)).isoformat(),
            "endTime": (end1 + timedelta(minutes=30)).isoformat(),
        },
        headers=mut(h),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "SCHEDULING_CONFLICT"
