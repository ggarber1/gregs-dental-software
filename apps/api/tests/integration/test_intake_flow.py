"""
Integration tests for the full digital intake form flow.

Covers the staff-initiates → patient-fills → staff-reviews → staff-applies pipeline
against a real Postgres database. Twilio SMS is mocked to avoid live sends.
"""

from __future__ import annotations

import uuid
from datetime import UTC
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import intake_submit_payload, mut

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_sms():
    """Prevent real SMS sends for all intake integration tests."""
    with patch("app.services.sms.send_sms", new=AsyncMock()) as m:
        yield m


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _fetch_token(db_session: AsyncSession, intake_form_id: str) -> str:
    """Retrieve the raw token for a form by ID — not exposed by the API."""
    from app.models.intake_form import IntakeForm

    form = await db_session.scalar(
        select(IntakeForm).where(IntakeForm.id == uuid.UUID(intake_form_id))
    )
    assert form is not None, "IntakeForm row not found in DB"
    return form.token


# ── Send ───────────────────────────────────────────────────────────────────────


class TestSendIntakeForm:
    async def test_send_creates_form_and_calls_sms(
        self, client: AsyncClient, auth_headers, patient, mock_sms
    ):
        resp = await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(patient.id)},
            headers=mut(auth_headers),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "intakeFormId" in body
        assert "expiresAt" in body
        mock_sms.assert_awaited_once()

    async def test_send_422_patient_no_phone(
        self, client: AsyncClient, auth_headers, db_session, practice, mock_sms
    ):
        from datetime import date

        from app.models.patient import Patient

        no_phone = Patient(
            id=uuid.uuid4(),
            practice_id=practice.id,
            first_name="No",
            last_name="Phone",
            date_of_birth=date(1985, 3, 10),
        )
        db_session.add(no_phone)
        await db_session.commit()

        resp = await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(no_phone.id)},
            headers=mut(auth_headers),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "PATIENT_NO_PHONE"
        mock_sms.assert_not_awaited()

    async def test_send_422_sms_opt_out(
        self, client: AsyncClient, auth_headers, db_session, practice, mock_sms
    ):
        from datetime import date

        from app.models.patient import Patient

        opted_out = Patient(
            id=uuid.uuid4(),
            practice_id=practice.id,
            first_name="Opted",
            last_name="Out",
            date_of_birth=date(1975, 7, 4),
            phone="+15550000001",
            sms_opt_out=True,
        )
        db_session.add(opted_out)
        await db_session.commit()

        resp = await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(opted_out.id)},
            headers=mut(auth_headers),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "PATIENT_SMS_OPT_OUT"

    async def test_send_404_unknown_patient(self, client: AsyncClient, auth_headers, mock_sms):
        resp = await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(uuid.uuid4())},
            headers=mut(auth_headers),
        )
        assert resp.status_code == 404

    async def test_send_404_wrong_practice(
        self, client: AsyncClient, db_session, mock_sms, staff_user, auth_headers, practice
    ):
        """Patient belonging to a different practice must not be found."""
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
            phone="+15550000002",
        )
        db_session.add(other_patient)
        await db_session.commit()

        resp = await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(other_patient.id)},
            headers=mut(auth_headers),
        )
        assert resp.status_code == 404


# ── Public endpoints ───────────────────────────────────────────────────────────


class TestPublicFormEndpoints:
    async def test_get_form_returns_greeting(
        self, client: AsyncClient, auth_headers, patient, db_session, practice, mock_sms
    ):
        send = await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(patient.id)},
            headers=mut(auth_headers),
        )
        assert send.status_code == 201
        token = await _fetch_token(db_session, send.json()["intakeFormId"])

        resp = await client.get(f"/api/intake/form/{token}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["practiceName"] == practice.name
        assert body["patientFirstName"] == patient.first_name

    async def test_get_form_404_unknown_token(self, client: AsyncClient):
        resp = await client.get("/api/intake/form/deadbeef" + "0" * 56)
        assert resp.status_code == 404

    async def test_submit_form_204(
        self, client: AsyncClient, auth_headers, patient, db_session, mock_sms
    ):
        send = await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(patient.id)},
            headers=mut(auth_headers),
        )
        token = await _fetch_token(db_session, send.json()["intakeFormId"])

        resp = await client.post(
            f"/api/intake/form/{token}/submit",
            json=intake_submit_payload(),
        )
        assert resp.status_code == 204

    async def test_submit_second_time_returns_410(
        self, client: AsyncClient, auth_headers, patient, db_session, mock_sms
    ):
        send = await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(patient.id)},
            headers=mut(auth_headers),
        )
        token = await _fetch_token(db_session, send.json()["intakeFormId"])
        payload = intake_submit_payload()

        first = await client.post(f"/api/intake/form/{token}/submit", json=payload)
        assert first.status_code == 204

        second = await client.post(f"/api/intake/form/{token}/submit", json=payload)
        assert second.status_code == 410
        assert second.json()["error"]["code"] == "INTAKE_COMPLETED"

    async def test_submit_requires_hipaa_consent(
        self, client: AsyncClient, auth_headers, patient, db_session, mock_sms
    ):
        send = await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(patient.id)},
            headers=mut(auth_headers),
        )
        token = await _fetch_token(db_session, send.json()["intakeFormId"])

        resp = await client.post(
            f"/api/intake/form/{token}/submit",
            json=intake_submit_payload(hipaaConsentAccepted=False),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "HIPAA_CONSENT_REQUIRED"

    async def test_get_form_returns_410_after_submission(
        self, client: AsyncClient, auth_headers, patient, db_session, mock_sms
    ):
        send = await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(patient.id)},
            headers=mut(auth_headers),
        )
        token = await _fetch_token(db_session, send.json()["intakeFormId"])

        await client.post(f"/api/intake/form/{token}/submit", json=intake_submit_payload())

        resp = await client.get(f"/api/intake/form/{token}")
        assert resp.status_code == 410
        assert resp.json()["error"]["code"] == "INTAKE_COMPLETED"


# ── Staff review endpoints ─────────────────────────────────────────────────────


class TestStaffIntakeEndpoints:
    async def test_list_intake_forms(
        self, client: AsyncClient, auth_headers, patient, db_session, mock_sms
    ):
        await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(patient.id)},
            headers=mut(auth_headers),
        )

        resp = await client.get("/api/v1/intake", headers=auth_headers)
        assert resp.status_code == 200
        forms = resp.json()
        assert len(forms) == 1
        assert forms[0]["status"] == "pending"

    async def test_list_filter_by_patient(
        self, client: AsyncClient, auth_headers, patient, db_session, practice, mock_sms
    ):
        from datetime import date

        from app.models.patient import Patient

        other = Patient(
            id=uuid.uuid4(),
            practice_id=practice.id,
            first_name="Bob",
            last_name="Smith",
            date_of_birth=date(1965, 11, 20),
            phone="+15550000003",
        )
        db_session.add(other)
        await db_session.commit()

        await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(patient.id)},
            headers=mut(auth_headers),
        )
        await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(other.id)},
            headers=mut(auth_headers),
        )

        resp = await client.get(f"/api/v1/intake?patient_id={patient.id}", headers=auth_headers)
        assert resp.status_code == 200
        forms = resp.json()
        assert len(forms) == 1
        assert forms[0]["patientId"] == str(patient.id)

    async def test_get_detail_returns_decrypted_responses(
        self, client: AsyncClient, auth_headers, patient, db_session, mock_sms
    ):
        send = await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(patient.id)},
            headers=mut(auth_headers),
        )
        form_id = send.json()["intakeFormId"]
        token = await _fetch_token(db_session, form_id)

        payload = intake_submit_payload(firstName="UpdatedFirst")
        await client.post(f"/api/intake/form/{token}/submit", json=payload)

        resp = await client.get(f"/api/v1/intake/{form_id}", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["responses"] is not None
        assert body["responses"]["firstName"] == "UpdatedFirst"

    async def test_get_detail_404_wrong_practice(
        self, client: AsyncClient, auth_headers, db_session, practice, mock_sms
    ):
        """A form belonging to a different practice must return 404."""
        import secrets
        from datetime import date, datetime, timedelta

        from app.models.intake_form import IntakeForm
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
        await db_session.flush()

        form = IntakeForm(
            id=uuid.uuid4(),
            practice_id=other_practice.id,
            patient_id=other_patient.id,
            token=secrets.token_hex(32),
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(hours=72),
            created_by=uuid.uuid4(),
        )
        db_session.add(form)
        await db_session.commit()

        resp = await client.get(f"/api/v1/intake/{form.id}", headers=auth_headers)
        assert resp.status_code == 404


# ── Apply ──────────────────────────────────────────────────────────────────────


class TestApplyIntakeForm:
    async def test_apply_updates_patient_record(
        self, client: AsyncClient, auth_headers, patient, db_session, mock_sms
    ):
        send = await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(patient.id)},
            headers=mut(auth_headers),
        )
        form_id = send.json()["intakeFormId"]
        token = await _fetch_token(db_session, form_id)

        payload = intake_submit_payload(
            firstName="Janet",
            lastName="Smith",
            phone="+15559990000",
            email="janet.smith@example.com",
            allergies=["penicillin", "latex"],
            medicalConditions=["diabetes"],
            medications=["metformin"],
            smsOptIn=False,
        )
        await client.post(f"/api/intake/form/{token}/submit", json=payload)

        resp = await client.post(f"/api/v1/intake/{form_id}/apply", headers=mut(auth_headers))
        assert resp.status_code == 200
        updated = resp.json()

        assert updated["firstName"] == "Janet"
        assert updated["lastName"] == "Smith"
        assert updated["phone"] == "+15559990000"
        assert updated["email"] == "janet.smith@example.com"
        assert "penicillin" in updated["allergies"]
        assert "latex" in updated["allergies"]
        # medicalConditions → medicalAlerts; medications → medications (separate)
        assert "diabetes" in updated["medicalAlerts"]
        assert "metformin" not in updated["medicalAlerts"]
        assert "metformin" in updated["medications"]
        # smsOptIn=False → smsOptOut=True
        assert updated["smsOptOut"] is True

    async def test_apply_422_form_not_completed(
        self, client: AsyncClient, auth_headers, patient, db_session, mock_sms
    ):
        send = await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(patient.id)},
            headers=mut(auth_headers),
        )
        form_id = send.json()["intakeFormId"]

        resp = await client.post(f"/api/v1/intake/{form_id}/apply", headers=mut(auth_headers))
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "INTAKE_NOT_COMPLETED"

    async def test_apply_idempotent(
        self, client: AsyncClient, auth_headers, patient, db_session, mock_sms
    ):
        """Applying twice should succeed and return the same patient state."""
        send = await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(patient.id)},
            headers=mut(auth_headers),
        )
        form_id = send.json()["intakeFormId"]
        token = await _fetch_token(db_session, form_id)

        payload = intake_submit_payload(firstName="Idempotent")
        await client.post(f"/api/intake/form/{token}/submit", json=payload)

        first = await client.post(f"/api/v1/intake/{form_id}/apply", headers=mut(auth_headers))
        second = await client.post(f"/api/v1/intake/{form_id}/apply", headers=mut(auth_headers))

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["firstName"] == second.json()["firstName"] == "Idempotent"


# ── Full happy-path flow ───────────────────────────────────────────────────────


class TestFullIntakeFlow:
    async def test_end_to_end(
        self, client: AsyncClient, auth_headers, patient, db_session, practice, mock_sms
    ):
        """
        End-to-end: staff sends → patient submits → staff reviews → staff applies.
        Verifies state transitions and DB persistence at each step.
        """
        from app.models.intake_form import IntakeForm

        # 1. Staff sends the form
        send_resp = await client.post(
            "/api/v1/intake/send",
            json={"patientId": str(patient.id)},
            headers=mut(auth_headers),
        )
        assert send_resp.status_code == 201
        form_id = send_resp.json()["intakeFormId"]
        mock_sms.assert_awaited_once()

        # 2. Confirm DB row is pending
        await db_session.refresh(
            await db_session.get(IntakeForm, uuid.UUID(form_id))  # type: ignore[arg-type]
        )
        db_form = await db_session.get(IntakeForm, uuid.UUID(form_id))
        assert db_form is not None
        assert db_form.status == "pending"
        assert db_form.responses_encrypted is None
        token = db_form.token

        # 3. Public: greeting
        greeting = await client.get(f"/api/intake/form/{token}")
        assert greeting.status_code == 200
        assert greeting.json()["practiceName"] == practice.name

        # 4. Public: submit
        submit_resp = await client.post(
            f"/api/intake/form/{token}/submit",
            json=intake_submit_payload(firstName="EndToEnd"),
        )
        assert submit_resp.status_code == 204

        # 5. Confirm DB row is completed and encrypted
        db_session.expire(db_form)
        db_form = await db_session.get(IntakeForm, uuid.UUID(form_id))
        assert db_form is not None
        assert db_form.status == "completed"
        assert db_form.responses_encrypted is not None

        # 6. Public token is now spent
        spent = await client.get(f"/api/intake/form/{token}")
        assert spent.status_code == 410

        # 7. Staff: list — 1 completed form
        list_resp = await client.get(
            f"/api/v1/intake?patient_id={patient.id}", headers=auth_headers
        )
        assert list_resp.status_code == 200
        forms_list = list_resp.json()
        assert len(forms_list) == 1
        assert forms_list[0]["status"] == "completed"

        # 8. Staff: detail with decrypted responses
        detail_resp = await client.get(f"/api/v1/intake/{form_id}", headers=auth_headers)
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["responses"]["firstName"] == "EndToEnd"

        # 9. Staff: apply — patient record updated
        apply_resp = await client.post(f"/api/v1/intake/{form_id}/apply", headers=mut(auth_headers))
        assert apply_resp.status_code == 200
        updated_patient = apply_resp.json()
        assert updated_patient["firstName"] == "EndToEnd"
