"""
Integration tests for Patient CRUD endpoints.

Exercises create / read / update / soft-delete against a real Postgres database.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from httpx import AsyncClient

from tests.integration.conftest import mut

pytestmark = pytest.mark.integration

_BASE_CREATE_BODY = {
    "firstName": "Alice",
    "lastName": "Walker",
    "dateOfBirth": "1985-04-20",
    "sex": "female",
    "phone": "+15550001111",
    "email": "alice@example.com",
    "addressLine1": "456 Elm St",
    "city": "Cambridge",
    "state": "MA",
    "zip": "02139",
    "allergies": ["sulfa"],
    "medicalAlerts": ["asthma"],
    "smsOptOut": False,
}


class TestCreatePatient:
    async def test_create_returns_201(self, client: AsyncClient, auth_headers):
        resp = await client.post(
            "/api/v1/patients", json=_BASE_CREATE_BODY, headers=mut(auth_headers)
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["firstName"] == "Alice"
        assert body["lastName"] == "Walker"
        assert body["phone"] == "+15550001111"
        assert "id" in body

    async def test_create_assigns_practice_id(self, client: AsyncClient, auth_headers, practice):
        resp = await client.post(
            "/api/v1/patients", json=_BASE_CREATE_BODY, headers=mut(auth_headers)
        )
        assert resp.status_code == 201
        assert resp.json()["practiceId"] == str(practice.id)

    async def test_create_422_missing_required_fields(self, client: AsyncClient, auth_headers):
        resp = await client.post(
            "/api/v1/patients",
            json={"firstName": "Incomplete"},
            headers=mut(auth_headers),
        )
        assert resp.status_code == 422

    async def test_create_400_practice_id_mismatch(self, client: AsyncClient, auth_headers):
        body = {**_BASE_CREATE_BODY, "practiceId": str(uuid.uuid4())}
        resp = await client.post("/api/v1/patients", json=body, headers=mut(auth_headers))
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "PRACTICE_ID_MISMATCH"


class TestGetPatient:
    async def test_get_returns_200(self, client: AsyncClient, auth_headers):
        create = await client.post(
            "/api/v1/patients", json=_BASE_CREATE_BODY, headers=mut(auth_headers)
        )
        patient_id = create.json()["id"]

        resp = await client.get(f"/api/v1/patients/{patient_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == patient_id

    async def test_get_404_unknown_id(self, client: AsyncClient, auth_headers):
        resp = await client.get(f"/api/v1/patients/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "PATIENT_NOT_FOUND"

    async def test_get_404_wrong_practice(self, client: AsyncClient, auth_headers, db_session):
        """A patient belonging to a different practice must not be visible."""
        from app.models.patient import Patient
        from app.models.practice import Practice

        other_practice = Practice(id=uuid.uuid4(), name="Other Dental", timezone="UTC")
        db_session.add(other_practice)
        await db_session.flush()

        other_patient = Patient(
            id=uuid.uuid4(),
            practice_id=other_practice.id,
            first_name="Bob",
            last_name="Other",
            date_of_birth=date(1970, 3, 5),
        )
        db_session.add(other_patient)
        await db_session.commit()

        resp = await client.get(f"/api/v1/patients/{other_patient.id}", headers=auth_headers)
        assert resp.status_code == 404


class TestUpdatePatient:
    async def test_patch_updates_fields(self, client: AsyncClient, auth_headers):
        create = await client.post(
            "/api/v1/patients", json=_BASE_CREATE_BODY, headers=mut(auth_headers)
        )
        patient_id = create.json()["id"]

        resp = await client.patch(
            f"/api/v1/patients/{patient_id}",
            json={"phone": "+15559990001", "city": "Somerville"},
            headers=mut(auth_headers),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["phone"] == "+15559990001"
        assert body["city"] == "Somerville"
        # Unchanged fields should remain
        assert body["firstName"] == "Alice"

    async def test_patch_is_partial(self, client: AsyncClient, auth_headers):
        """Omitting a field must not overwrite it with null."""
        create = await client.post(
            "/api/v1/patients", json=_BASE_CREATE_BODY, headers=mut(auth_headers)
        )
        patient_id = create.json()["id"]

        resp = await client.patch(
            f"/api/v1/patients/{patient_id}",
            json={"lastName": "NewLastName"},
            headers=mut(auth_headers),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["lastName"] == "NewLastName"
        assert body["firstName"] == "Alice"  # untouched

    async def test_patch_404_unknown_id(self, client: AsyncClient, auth_headers):
        resp = await client.patch(
            f"/api/v1/patients/{uuid.uuid4()}",
            json={"phone": "+15550002222"},
            headers=mut(auth_headers),
        )
        assert resp.status_code == 404

    async def test_patch_updates_dental_history_fields(self, client: AsyncClient, auth_headers):
        create = await client.post(
            "/api/v1/patients", json=_BASE_CREATE_BODY, headers=mut(auth_headers)
        )
        patient_id = create.json()["id"]

        resp = await client.patch(
            f"/api/v1/patients/{patient_id}",
            json={
                "lastDentalVisit": "About 2 years ago",
                "previousDentist": "Dr. Johnson",
                "lastXrayDate": "2023-11-15",
                "dentalSymptoms": ["Sensitivity to cold", "Bleeding gums"],
            },
            headers=mut(auth_headers),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["lastDentalVisit"] == "About 2 years ago"
        assert body["previousDentist"] == "Dr. Johnson"
        assert body["lastXrayDate"] == "2023-11-15"
        assert body["dentalSymptoms"] == ["Sensitivity to cold", "Bleeding gums"]
        # Unrelated fields must be unchanged
        assert body["firstName"] == "Alice"


class TestDeletePatient:
    async def test_delete_soft_deletes(self, client: AsyncClient, auth_headers):
        create = await client.post(
            "/api/v1/patients", json=_BASE_CREATE_BODY, headers=mut(auth_headers)
        )
        patient_id = create.json()["id"]

        delete_resp = await client.delete(
            f"/api/v1/patients/{patient_id}", headers=mut(auth_headers)
        )
        assert delete_resp.status_code == 204

        get_resp = await client.get(f"/api/v1/patients/{patient_id}", headers=auth_headers)
        assert get_resp.status_code == 404

    async def test_delete_404_unknown_id(self, client: AsyncClient, auth_headers):
        resp = await client.delete(f"/api/v1/patients/{uuid.uuid4()}", headers=mut(auth_headers))
        assert resp.status_code == 404

    async def test_deleted_patient_excluded_from_list(self, client: AsyncClient, auth_headers):
        create = await client.post(
            "/api/v1/patients", json=_BASE_CREATE_BODY, headers=mut(auth_headers)
        )
        patient_id = create.json()["id"]

        await client.delete(f"/api/v1/patients/{patient_id}", headers=mut(auth_headers))

        # Search by last name — should come back empty
        resp = await client.get("/api/v1/patients?q=Walker", headers=auth_headers)
        assert resp.status_code == 200
        results = resp.json()
        patients = results.get("data", results) if isinstance(results, dict) else results
        ids = [p["id"] for p in patients]
        assert patient_id not in ids


class TestListPatients:
    async def test_list_returns_practice_patients_only(
        self, client: AsyncClient, auth_headers, db_session
    ):
        """Patients from other practices must not appear in list results."""
        from app.models.patient import Patient
        from app.models.practice import Practice

        other_practice = Practice(id=uuid.uuid4(), name="Rival Dental", timezone="UTC")
        db_session.add(other_practice)
        await db_session.flush()

        rival_patient = Patient(
            id=uuid.uuid4(),
            practice_id=other_practice.id,
            first_name="Rival",
            last_name="Patient",
            date_of_birth=date(1990, 1, 1),
        )
        db_session.add(rival_patient)
        await db_session.commit()

        await client.post("/api/v1/patients", json=_BASE_CREATE_BODY, headers=mut(auth_headers))

        resp = await client.get("/api/v1/patients?q=", headers=auth_headers)
        assert resp.status_code == 200
        result_body = resp.json()
        # Handle both list and paginated dict response shapes
        patients = (
            result_body.get("data", result_body) if isinstance(result_body, dict) else result_body
        )
        ids = [p["id"] for p in patients]
        assert str(rival_patient.id) not in ids
