"""
Integration tests for the patient insurance CRUD endpoints.

Covers:
  - Happy path: create, GET list, PATCH, DELETE
  - Practice scoping: insurance from another practice is invisible
  - Soft delete: deleted records do not appear in list
  - Role auth: read_only cannot write; front_desk can
  - Intake apply: applying a completed intake form with a carrier
    creates / replaces a primary patient_insurance row
"""

from __future__ import annotations

import uuid
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import intake_submit_payload, mut

# Patch targets used throughout role-based access tests
_P_HEADER = "app.middleware.auth.jwt.get_unverified_header"
_P_KEY = "app.middleware.auth._get_public_key"
_P_DECODE = "app.middleware.auth.jwt.decode"

pytestmark = pytest.mark.integration


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _create_insurance(
    client: AsyncClient,
    auth_headers: dict,
    patient_id: str,
    **overrides: object,
) -> dict:
    """POST a valid insurance record and assert 201."""
    body = {
        "priority": "primary",
        "carrier": "Delta Dental",
        "memberId": "DD123456",
        "groupNumber": "GRP001",
        "relationshipToInsured": "self",
        **overrides,
    }
    resp = await client.post(
        f"/api/v1/patients/{patient_id}/insurance",
        json=body,
        headers=mut(auth_headers),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
def mock_sms():
    with patch("app.services.sms.send_sms", new=AsyncMock()) as m:
        yield m


async def _fetch_intake_token(db_session: AsyncSession, form_id: str) -> str:
    from app.models.intake_form import IntakeForm

    form = await db_session.scalar(select(IntakeForm).where(IntakeForm.id == uuid.UUID(form_id)))
    assert form is not None
    return form.token


# ── List / Create ──────────────────────────────────────────────────────────────


class TestListAndCreate:
    async def test_list_empty_before_any_insurance(
        self, client: AsyncClient, auth_headers, patient
    ):
        resp = await client.get(f"/api/v1/patients/{patient.id}/insurance", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_returns_201_with_fields(self, client: AsyncClient, auth_headers, patient):
        created = await _create_insurance(client, auth_headers, str(patient.id))
        assert created["carrier"] == "Delta Dental"
        assert created["memberId"] == "DD123456"
        assert created["groupNumber"] == "GRP001"
        assert created["priority"] == "primary"
        assert created["patientId"] == str(patient.id)
        assert "id" in created

    async def test_list_returns_created_record(self, client: AsyncClient, auth_headers, patient):
        await _create_insurance(client, auth_headers, str(patient.id))

        resp = await client.get(f"/api/v1/patients/{patient.id}/insurance", headers=auth_headers)
        assert resp.status_code == 200
        records = resp.json()
        assert len(records) == 1
        assert records[0]["carrier"] == "Delta Dental"

    async def test_create_with_non_self_relationship_stores_insured_details(
        self, client: AsyncClient, auth_headers, patient
    ):
        created = await _create_insurance(
            client,
            auth_headers,
            str(patient.id),
            relationshipToInsured="spouse",
            insuredFirstName="John",
            insuredLastName="Doe",
            insuredDateOfBirth="1988-05-20",
        )
        assert created["relationshipToInsured"] == "spouse"
        assert created["insuredFirstName"] == "John"
        assert created["insuredLastName"] == "Doe"
        assert created["insuredDateOfBirth"] == "1988-05-20"

    async def test_create_422_missing_carrier(self, client: AsyncClient, auth_headers, patient):
        resp = await client.post(
            f"/api/v1/patients/{patient.id}/insurance",
            json={"priority": "primary", "relationshipToInsured": "self"},
            headers=mut(auth_headers),
        )
        assert resp.status_code == 422

    async def test_list_is_scoped_to_patient(
        self, client: AsyncClient, auth_headers, patient, db_session, practice
    ):
        """Insurance for patient A must not appear when listing patient B's insurance."""
        from datetime import date

        from app.models.patient import Patient

        other = Patient(
            id=uuid.uuid4(),
            practice_id=practice.id,
            first_name="Other",
            last_name="Patient",
            date_of_birth=date(1975, 1, 1),
        )
        db_session.add(other)
        await db_session.commit()

        await _create_insurance(client, auth_headers, str(patient.id))

        resp = await client.get(f"/api/v1/patients/{other.id}/insurance", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []


# ── Update ────────────────────────────────────────────────────────────────────


class TestUpdate:
    async def test_patch_updates_carrier_and_member_id(
        self, client: AsyncClient, auth_headers, patient
    ):
        created = await _create_insurance(client, auth_headers, str(patient.id))
        insurance_id = created["id"]

        resp = await client.patch(
            f"/api/v1/patients/{patient.id}/insurance/{insurance_id}",
            json={"carrier": "Cigna", "memberId": "CIG999"},
            headers=mut(auth_headers),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["carrier"] == "Cigna"
        assert body["memberId"] == "CIG999"
        # Unchanged fields survive
        assert body["groupNumber"] == "GRP001"

    async def test_patch_is_partial(self, client: AsyncClient, auth_headers, patient):
        created = await _create_insurance(client, auth_headers, str(patient.id))

        resp = await client.patch(
            f"/api/v1/patients/{patient.id}/insurance/{created['id']}",
            json={"priority": "secondary"},
            headers=mut(auth_headers),
        )
        assert resp.status_code == 200
        assert resp.json()["priority"] == "secondary"
        assert resp.json()["carrier"] == "Delta Dental"  # untouched

    async def test_patch_404_unknown_insurance(self, client: AsyncClient, auth_headers, patient):
        resp = await client.patch(
            f"/api/v1/patients/{patient.id}/insurance/{uuid.uuid4()}",
            json={"carrier": "Aetna"},
            headers=mut(auth_headers),
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "INSURANCE_NOT_FOUND"


# ── Delete ────────────────────────────────────────────────────────────────────


class TestDelete:
    async def test_delete_returns_204(self, client: AsyncClient, auth_headers, patient):
        created = await _create_insurance(client, auth_headers, str(patient.id))
        insurance_id = created["id"]

        resp = await client.delete(
            f"/api/v1/patients/{patient.id}/insurance/{insurance_id}",
            headers=mut(auth_headers),
        )
        assert resp.status_code == 204

    async def test_soft_delete_excluded_from_list(self, client: AsyncClient, auth_headers, patient):
        created = await _create_insurance(client, auth_headers, str(patient.id))
        insurance_id = created["id"]

        await client.delete(
            f"/api/v1/patients/{patient.id}/insurance/{insurance_id}",
            headers=mut(auth_headers),
        )

        resp = await client.get(f"/api/v1/patients/{patient.id}/insurance", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_soft_delete_sets_deleted_at_in_db(
        self, client: AsyncClient, auth_headers, patient, db_session
    ):
        from app.models.patient_insurance import PatientInsurance

        created = await _create_insurance(client, auth_headers, str(patient.id))
        insurance_id = created["id"]

        await client.delete(
            f"/api/v1/patients/{patient.id}/insurance/{insurance_id}",
            headers=mut(auth_headers),
        )

        row = await db_session.scalar(
            select(PatientInsurance).where(PatientInsurance.id == uuid.UUID(insurance_id))
        )
        assert row is not None
        assert row.deleted_at is not None, "deleted_at must be set after soft delete"

    async def test_delete_404_unknown_insurance(self, client: AsyncClient, auth_headers, patient):
        resp = await client.delete(
            f"/api/v1/patients/{patient.id}/insurance/{uuid.uuid4()}",
            headers=mut(auth_headers),
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "INSURANCE_NOT_FOUND"


# ── Practice scoping ──────────────────────────────────────────────────────────


class TestPracticeScoping:
    async def test_cannot_read_insurance_for_other_practice_patient(
        self, client: AsyncClient, auth_headers, db_session
    ):
        from datetime import date

        from app.models.patient import Patient
        from app.models.practice import Practice

        other_practice = Practice(id=uuid.uuid4(), name="Other Clinic", timezone="UTC")
        db_session.add(other_practice)
        await db_session.flush()

        other_patient = Patient(
            id=uuid.uuid4(),
            practice_id=other_practice.id,
            first_name="Alice",
            last_name="Other",
            date_of_birth=date(1980, 1, 1),
        )
        db_session.add(other_patient)
        await db_session.commit()

        # Creating insurance directly in DB for the other practice's patient
        from app.models.patient_insurance import PatientInsurance

        ins = PatientInsurance(
            id=uuid.uuid4(),
            patient_id=other_patient.id,
            practice_id=other_practice.id,
            priority="primary",
            carrier="Cigna",
            relationship_to_insured="self",
            is_active=True,
        )
        db_session.add(ins)
        await db_session.commit()

        # Requesting list through our practice-scoped client should return empty
        resp = await client.get(
            f"/api/v1/patients/{other_patient.id}/insurance", headers=auth_headers
        )
        # Either 200 empty or 404 depending on patient scoping — both are safe
        if resp.status_code == 200:
            assert resp.json() == []


# ── Role-based access ─────────────────────────────────────────────────────────


async def _make_user_with_role(db_session, practice, role: str):  # type: ignore[no-untyped-def]
    """Insert a User + PracticeUser with the given role. Returns (user, cognito_sub)."""
    from app.models.user import PracticeUser, User

    cognito_sub = f"{role}-sub-{uuid.uuid4().hex}"
    user = User(
        id=uuid.uuid4(),
        cognito_sub=cognito_sub,
        email=f"{role}-{uuid.uuid4().hex[:6]}@sunrise.test",
        full_name=role.title(),
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    pu = PracticeUser(
        practice_id=practice.id,
        user_id=user.id,
        role=role,
        is_active=True,
    )
    db_session.add(pu)
    await db_session.commit()
    return user, cognito_sub


def _auth_patches(cognito_sub: str, email: str, groups: list[str]) -> ExitStack:
    """Return an ExitStack with all three auth middleware patches active."""
    stack = ExitStack()
    stack.enter_context(patch(_P_HEADER, return_value={"kid": "test-kid"}))
    stack.enter_context(patch(_P_KEY, new=AsyncMock(return_value="fake-public-key")))
    stack.enter_context(
        patch(
            _P_DECODE,
            return_value={"sub": cognito_sub, "email": email, "cognito:groups": groups},
        )
    )
    return stack


class TestRoleBasedAccess:
    async def test_read_only_can_list_insurance(
        self, client: AsyncClient, auth_headers, patient, db_session, practice
    ):
        await _create_insurance(client, auth_headers, str(patient.id))
        user, cognito_sub = await _make_user_with_role(db_session, practice, "read_only")

        with _auth_patches(cognito_sub, user.email, ["read_only"]):
            resp = await client.get(
                f"/api/v1/patients/{patient.id}/insurance",
                headers={
                    "Authorization": "Bearer test-token",
                    "X-Practice-ID": str(practice.id),
                },
            )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_read_only_cannot_create_insurance(
        self, client: AsyncClient, patient, db_session, practice
    ):
        user, cognito_sub = await _make_user_with_role(db_session, practice, "read_only")

        with _auth_patches(cognito_sub, user.email, ["read_only"]):
            resp = await client.post(
                f"/api/v1/patients/{patient.id}/insurance",
                json={
                    "priority": "primary",
                    "carrier": "Delta Dental",
                    "relationshipToInsured": "self",
                },
                headers={
                    "Authorization": "Bearer test-token",
                    "X-Practice-ID": str(practice.id),
                    "Idempotency-Key": str(uuid.uuid4()),
                },
            )
        assert resp.status_code == 403

    async def test_read_only_cannot_delete_insurance(
        self, client: AsyncClient, auth_headers, patient, db_session, practice
    ):
        created = await _create_insurance(client, auth_headers, str(patient.id))
        user, cognito_sub = await _make_user_with_role(db_session, practice, "read_only")

        with _auth_patches(cognito_sub, user.email, ["read_only"]):
            resp = await client.delete(
                f"/api/v1/patients/{patient.id}/insurance/{created['id']}",
                headers={
                    "Authorization": "Bearer test-token",
                    "X-Practice-ID": str(practice.id),
                    "Idempotency-Key": str(uuid.uuid4()),
                },
            )
        assert resp.status_code == 403

    async def test_front_desk_can_create_insurance(
        self, client: AsyncClient, patient, db_session, practice
    ):
        """front_desk role must be able to create insurance (write role)."""
        user, cognito_sub = await _make_user_with_role(db_session, practice, "front_desk")

        with _auth_patches(cognito_sub, user.email, ["front_desk"]):
            resp = await client.post(
                f"/api/v1/patients/{patient.id}/insurance",
                json={
                    "priority": "primary",
                    "carrier": "Aetna",
                    "relationshipToInsured": "self",
                },
                headers={
                    "Authorization": "Bearer test-token",
                    "X-Practice-ID": str(practice.id),
                    "Idempotency-Key": str(uuid.uuid4()),
                },
            )
        assert resp.status_code == 201


# ── Intake apply → insurance ───────────────────────────────────────────────────


class TestIntakeApplyCreatesInsurance:
    async def test_apply_with_carrier_creates_primary_insurance(
        self,
        client: AsyncClient,
        auth_headers,
        patient,
        db_session,
        mock_sms,
    ):
        """Applying an intake form with an insurance carrier must create a
        patient_insurance row with priority='primary'."""
        send = await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(patient.id)},
            headers=mut(auth_headers),
        )
        form_id = send.json()["intakeFormId"]
        token = await _fetch_intake_token(db_session, form_id)

        await client.post(
            f"/api/intake/form/{token}/submit",
            json=intake_submit_payload(
                insuranceCarrier="MetLife",
                insuranceMemberId="ML-999",
                insuranceGroupNumber="GRP-ML",
                relationshipToInsured="self",
            ),
        )

        apply_resp = await client.post(f"/api/v1/intake/{form_id}/apply", headers=mut(auth_headers))
        assert apply_resp.status_code == 200

        ins_resp = await client.get(
            f"/api/v1/patients/{patient.id}/insurance", headers=auth_headers
        )
        assert ins_resp.status_code == 200
        records = ins_resp.json()
        assert len(records) == 1
        ins = records[0]
        assert ins["carrier"] == "MetLife"
        assert ins["memberId"] == "ML-999"
        assert ins["groupNumber"] == "GRP-ML"
        assert ins["priority"] == "primary"

    async def test_apply_without_carrier_does_not_create_insurance(
        self,
        client: AsyncClient,
        auth_headers,
        patient,
        db_session,
        mock_sms,
    ):
        """If insuranceCarrier is empty/omitted, no insurance row should be created."""
        send = await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(patient.id)},
            headers=mut(auth_headers),
        )
        form_id = send.json()["intakeFormId"]
        token = await _fetch_intake_token(db_session, form_id)

        await client.post(
            f"/api/intake/form/{token}/submit",
            json=intake_submit_payload(insuranceCarrier=""),
        )

        apply_resp = await client.post(f"/api/v1/intake/{form_id}/apply", headers=mut(auth_headers))
        assert apply_resp.status_code == 200

        ins_resp = await client.get(
            f"/api/v1/patients/{patient.id}/insurance", headers=auth_headers
        )
        assert ins_resp.status_code == 200
        assert ins_resp.json() == []

    async def test_apply_replaces_existing_primary_insurance(
        self,
        client: AsyncClient,
        auth_headers,
        patient,
        db_session,
        mock_sms,
    ):
        """A second apply with a different carrier should soft-delete the old
        primary record and create a fresh one."""
        # Pre-load existing primary insurance
        await _create_insurance(client, auth_headers, str(patient.id), carrier="Cigna")

        send = await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(patient.id)},
            headers=mut(auth_headers),
        )
        form_id = send.json()["intakeFormId"]
        token = await _fetch_intake_token(db_session, form_id)

        await client.post(
            f"/api/intake/form/{token}/submit",
            json=intake_submit_payload(insuranceCarrier="Aetna", insuranceMemberId="AET-001"),
        )

        await client.post(f"/api/v1/intake/{form_id}/apply", headers=mut(auth_headers))

        ins_resp = await client.get(
            f"/api/v1/patients/{patient.id}/insurance", headers=auth_headers
        )
        records = ins_resp.json()
        # Only one active primary record
        primaries = [r for r in records if r["priority"] == "primary"]
        assert len(primaries) == 1
        assert primaries[0]["carrier"] == "Aetna"
