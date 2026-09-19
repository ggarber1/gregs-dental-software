"""Integration tests for statement generation (service + HTTP)."""

from __future__ import annotations

import datetime
import uuid
from datetime import UTC, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger_entry import LedgerEntry
from app.models.patient import Patient
from app.models.patient_statement import PatientStatement
from app.models.practice import Practice
from app.models.user import PracticeUser, User
from app.services.statements import service as statements
from tests.integration.conftest import mut

pytestmark = pytest.mark.integration

_NOW = datetime.datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
_FAKE_PDF = b"%PDF-1.7 fake statement"

# Patch targets — both are imported by name into the service module.
_P_PDF = "app.services.statements.service.html_to_pdf"
_P_SEND = "app.services.statements.service.send_email_with_attachment"

# Auth patch targets (mirrored from test_ledger_endpoints.py)
_P_HEADER = "app.middleware.auth.jwt.get_unverified_header"
_P_KEY = "app.middleware.auth._get_public_key"
_P_DECODE = "app.middleware.auth.jwt.decode"


async def _seed(
    session: AsyncSession,
    *,
    ledger_enabled: bool = True,
    role: str = "admin",
    email: str | None = "pat@example.test",
):
    practice = Practice(
        id=uuid.uuid4(),
        name="Statement Test Practice",
        phone="+16175550100",
        address_line1="1 Main St",
        city="Boston",
        state="MA",
        zip="02110",
        features={"billing_ledger": ledger_enabled},
    )
    session.add(practice)

    cognito_sub = f"stmt-sub-{uuid.uuid4().hex}"
    user = User(
        id=uuid.uuid4(),
        cognito_sub=cognito_sub,
        email=f"stmt-staff-{uuid.uuid4().hex[:6]}@test.local",
        full_name="Statement Staff",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    session.add(PracticeUser(practice_id=practice.id, user_id=user.id, role=role, is_active=True))

    patient = Patient(
        id=uuid.uuid4(),
        practice_id=practice.id,
        first_name="Pat",
        last_name="Statement",
        date_of_birth=datetime.date(1990, 1, 1),
        email=email,
        address_line1="9 Elm Rd",
        city="Cambridge",
        state="MA",
        zip="02139",
    )
    session.add(patient)
    await session.commit()
    return practice, user, cognito_sub, patient


async def _post(
    session: AsyncSession,
    practice_id: uuid.UUID,
    patient_id: uuid.UUID,
    *,
    entry_type: str = "charge",
    amount_cents: int,
    days_ago: int = 1,
    reverses: uuid.UUID | None = None,
) -> LedgerEntry:
    entry = LedgerEntry(
        id=uuid.uuid4(),
        practice_id=practice_id,
        patient_id=patient_id,
        entry_type=entry_type,
        amount_cents=amount_cents,
        reverses_entry_id=reverses,
        posted_at=_NOW - timedelta(days=days_ago),
    )
    session.add(entry)
    await session.commit()
    return entry


async def _statement_rows(session: AsyncSession, patient_id: uuid.UUID) -> list[PatientStatement]:
    rows = await session.scalars(
        select(PatientStatement)
        .where(PatientStatement.patient_id == patient_id)
        .order_by(PatientStatement.generated_at)
    )
    return list(rows)


def _decoded(user, cognito_sub, groups=("admin",)):
    return {"sub": cognito_sub, "email": user.email, "cognito:groups": list(groups)}


def _auth_patches(decoded):
    return (
        patch(_P_HEADER, return_value={"kid": "test-kid"}),
        patch(_P_KEY, new=AsyncMock(return_value="fake-public-key")),
        patch(_P_DECODE, return_value=decoded),
    )


# ── Service ───────────────────────────────────────────────────────────────────


class TestCreateStatementService:
    async def test_email_sends_pdf_and_records_delivered(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=10000, days_ago=45)
        await _post(
            db_session, practice.id, patient.id, entry_type="patient_payment", amount_cents=-2500
        )

        send = AsyncMock(return_value="ses-msg-1")
        with patch(_P_PDF, return_value=_FAKE_PDF), patch(_P_SEND, send):
            row = await statements.create_statement(
                db_session,
                practice.id,
                patient.id,
                delivery_method="email",
                generated_by="user-sub-1",
                now=_NOW,
            )

        assert row.delivery_method == "email"
        assert row.balance_cents == 7500
        assert row.aging_snapshot == {"b0_30": 0, "b31_60": 10000, "b61_90": 0, "b90_plus": 0}
        assert row.generated_at == _NOW
        assert row.delivered_at == _NOW
        assert row.generated_by == "user-sub-1"
        kwargs = send.call_args.kwargs
        assert kwargs["to"] == "pat@example.test"
        assert kwargs["subject"] == "Statement from Statement Test Practice"
        assert kwargs["from_name"] == "Statement Test Practice"
        assert kwargs["attachment_bytes"] == _FAKE_PDF
        assert kwargs["attachment_filename"] == "statement-2026-09-18.pdf"
        assert "$75.00" in kwargs["text_body"]
        assert len(await _statement_rows(db_session, patient.id)) == 1

    async def test_download_records_without_sending(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)

        send = AsyncMock()
        with patch(_P_PDF) as pdf, patch(_P_SEND, send):
            row = await statements.create_statement(
                db_session,
                practice.id,
                patient.id,
                delivery_method="download",
                generated_by="user-sub-1",
                now=_NOW,
            )

        assert row.delivery_method == "download"
        assert row.delivered_at is None
        send.assert_not_called()
        pdf.assert_not_called()

    async def test_zero_balance_rejected(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)
        await _post(
            db_session, practice.id, patient.id, entry_type="patient_payment", amount_cents=-600
        )

        with pytest.raises(statements.NoOutstandingBalanceError):
            await statements.create_statement(
                db_session, practice.id, patient.id, delivery_method="download", generated_by="u"
            )
        assert await _statement_rows(db_session, patient.id) == []

    async def test_email_without_address_rejected(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session, email=None)
        await _post(db_session, practice.id, patient.id, amount_cents=600)

        with pytest.raises(statements.NoPatientEmailError):
            await statements.create_statement(
                db_session, practice.id, patient.id, delivery_method="email", generated_by="u"
            )
        assert await _statement_rows(db_session, patient.id) == []

    async def test_ses_failure_records_nothing(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)

        with (
            patch(_P_PDF, return_value=_FAKE_PDF),
            patch(_P_SEND, AsyncMock(side_effect=RuntimeError("SES send_raw_email failed"))),
            pytest.raises(statements.StatementDeliveryError),
        ):
            await statements.create_statement(
                db_session, practice.id, patient.id, delivery_method="email", generated_by="u"
            )
        assert await _statement_rows(db_session, patient.id) == []

    async def test_email_opt_out_is_ignored_for_statements(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        patient.email_opt_out = True
        await db_session.commit()
        await _post(db_session, practice.id, patient.id, amount_cents=600)

        send = AsyncMock(return_value="ses-msg-2")
        with patch(_P_PDF, return_value=_FAKE_PDF), patch(_P_SEND, send):
            await statements.create_statement(
                db_session, practice.id, patient.id, delivery_method="email", generated_by="u"
            )
        send.assert_awaited_once()

    async def test_wrong_practice_is_lookup_error(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        other, _, _, _ = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)

        with pytest.raises(LookupError):
            await statements.create_statement(
                db_session, other.id, patient.id, delivery_method="download", generated_by="u"
            )

    async def test_soft_deleted_patient_is_lookup_error(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)
        patient.deleted_at = _NOW
        await db_session.commit()

        with pytest.raises(LookupError):
            await statements.create_statement(
                db_session, practice.id, patient.id, delivery_method="download", generated_by="u"
            )

    async def test_dev_no_send_still_records_delivered_at(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)

        with patch(_P_PDF, return_value=_FAKE_PDF), patch(_P_SEND, AsyncMock(return_value=None)):
            row = await statements.create_statement(
                db_session,
                practice.id,
                patient.id,
                delivery_method="email",
                generated_by="u",
                now=_NOW,
            )
        assert row.delivered_at == _NOW


class TestListAndRenderService:
    async def test_list_is_most_recent_first_and_practice_scoped(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        other, _, _, _ = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)
        with patch(_P_PDF, return_value=_FAKE_PDF), patch(_P_SEND, AsyncMock(return_value="m")):
            first = await statements.create_statement(
                db_session,
                practice.id,
                patient.id,
                delivery_method="download",
                generated_by="u",
                now=_NOW - timedelta(days=1),
            )
            second = await statements.create_statement(
                db_session,
                practice.id,
                patient.id,
                delivery_method="email",
                generated_by="u",
                now=_NOW,
            )

        mine = await statements.list_statements(db_session, practice.id, patient.id)
        theirs = await statements.list_statements(db_session, other.id, patient.id)

        assert [s.id for s in mine] == [second.id, first.id]
        assert theirs == []
        assert await statements.get_statement(db_session, other.id, patient.id, first.id) is None
        found = await statements.get_statement(db_session, practice.id, patient.id, first.id)
        assert found is not None and found.id == first.id

    async def test_render_uses_live_ledger_and_excludes_reversals(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=1000, days_ago=2)
        wrong = await _post(db_session, practice.id, patient.id, amount_cents=9000, days_ago=3)
        await _post(db_session, practice.id, patient.id, amount_cents=-9000, reverses=wrong.id)

        captured: dict[str, str] = {}

        def fake_pdf(html: str) -> bytes:
            captured["html"] = html
            return _FAKE_PDF

        with patch(_P_PDF, side_effect=fake_pdf):
            pdf = await statements.render_statement_pdf(
                db_session, practice.id, patient.id, statement_date=_NOW.date()
            )

        assert pdf == _FAKE_PDF
        assert "$10.00" in captured["html"]
        assert "$90.00" not in captured["html"]
        assert "Pat Statement" in captured["html"]

    async def test_render_without_require_balance_works_after_full_payment(
        self, db_session: AsyncSession
    ):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)
        await _post(
            db_session, practice.id, patient.id, entry_type="patient_payment", amount_cents=-600
        )

        with patch(_P_PDF, return_value=_FAKE_PDF):
            pdf = await statements.render_statement_pdf(
                db_session, practice.id, patient.id, statement_date=_NOW.date()
            )
        assert pdf == _FAKE_PDF

    async def test_render_preview_requires_balance(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        with pytest.raises(statements.NoOutstandingBalanceError):
            await statements.render_statement_pdf(
                db_session,
                practice.id,
                patient.id,
                statement_date=_NOW.date(),
                require_balance=True,
            )


# ── HTTP ──────────────────────────────────────────────────────────────────────


def _headers(practice: Practice) -> dict[str, str]:
    return {"Authorization": "Bearer test-token", "X-Practice-ID": str(practice.id)}


class TestStatementsHttp:
    async def test_email_then_history_then_aging(self, client, db_session: AsyncSession):
        practice, user, sub, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=12000, days_ago=40)
        headers = _headers(practice)
        base = f"/api/v1/patients/{patient.id}/statements"
        h, k, d = _auth_patches(_decoded(user, sub))

        send = AsyncMock(return_value="ses-msg-http")
        with h, k, d, patch(_P_PDF, return_value=_FAKE_PDF), patch(_P_SEND, send):
            create = await client.post(base, headers=mut(headers), json={"deliveryMethod": "email"})
            assert create.status_code == 201, create.text
            body = create.json()
            assert body["deliveryMethod"] == "email"
            assert body["balanceCents"] == 12000
            assert body["buckets"]["b31_60"] == 12000
            assert body["deliveredAt"] is not None
            assert body["generatedBy"] == sub
            send.assert_awaited_once()

            history = await client.get(base, headers=headers)
            assert history.status_code == 200, history.text
            assert [s["id"] for s in history.json()] == [body["id"]]

            aging = await client.get("/api/v1/reports/patient-aging", headers=headers)
            assert aging.status_code == 200, aging.text
            rows = aging.json()
            assert len(rows) == 1
            assert rows[0]["patientId"] == str(patient.id)
            assert rows[0]["lastStatementMethod"] == "email"
            assert rows[0]["lastStatementAt"] == body["generatedAt"]

    async def test_download_flow_post_then_get_pdf(self, client, db_session: AsyncSession):
        practice, user, sub, patient = await _seed(db_session, email=None)
        await _post(db_session, practice.id, patient.id, amount_cents=600)
        headers = _headers(practice)
        base = f"/api/v1/patients/{patient.id}/statements"
        h, k, d = _auth_patches(_decoded(user, sub))

        with h, k, d, patch(_P_PDF, return_value=_FAKE_PDF):
            create = await client.post(
                base, headers=mut(headers), json={"deliveryMethod": "download"}
            )
            assert create.status_code == 201, create.text
            assert create.json()["deliveredAt"] is None
            statement_id = create.json()["id"]

            pdf = await client.get(f"{base}/{statement_id}/pdf", headers=headers)
            assert pdf.status_code == 200, pdf.text
            assert pdf.headers["content-type"] == "application/pdf"
            assert pdf.headers["content-disposition"].startswith("attachment;")
            assert pdf.content == _FAKE_PDF

            preview = await client.get(f"{base}/preview", headers=headers)
            assert preview.status_code == 200, preview.text
            assert preview.headers["content-disposition"].startswith("inline;")

        assert len(await _statement_rows(db_session, patient.id)) == 1  # preview recorded nothing

    async def test_idempotent_replay_returns_json_not_pdf(self, client, db_session: AsyncSession):
        practice, user, sub, patient = await _seed(db_session, email=None)
        await _post(db_session, practice.id, patient.id, amount_cents=600)
        headers = {**_headers(practice), "Idempotency-Key": str(uuid.uuid4())}
        base = f"/api/v1/patients/{patient.id}/statements"
        h, k, d = _auth_patches(_decoded(user, sub))
        body = {"deliveryMethod": "download"}

        with h, k, d:
            first = await client.post(base, headers=headers, json=body)
            assert first.status_code == 201, first.text
            assert "X-Idempotent-Replayed" not in first.headers

            second = await client.post(base, headers=headers, json=body)
            assert second.status_code == 201, second.text
            assert second.headers["X-Idempotent-Replayed"] == "true"
            assert second.headers["content-type"].startswith("application/json")
            assert second.json() == first.json()

        assert len(await _statement_rows(db_session, patient.id)) == 1

    async def test_validation_errors(self, client, db_session: AsyncSession):
        practice, user, sub, patient = await _seed(db_session, email=None)
        headers = _headers(practice)
        base = f"/api/v1/patients/{patient.id}/statements"
        h, k, d = _auth_patches(_decoded(user, sub))

        with h, k, d:
            no_balance = await client.post(
                base, headers=mut(headers), json={"deliveryMethod": "download"}
            )
            assert no_balance.status_code == 400
            assert no_balance.json()["error"]["code"] == "NO_OUTSTANDING_BALANCE"

            await _post(db_session, practice.id, patient.id, amount_cents=600)
            no_email = await client.post(
                base, headers=mut(headers), json={"deliveryMethod": "email"}
            )
            assert no_email.status_code == 400
            assert no_email.json()["error"]["code"] == "PATIENT_HAS_NO_EMAIL"

            missing_key = await client.post(
                base, headers=headers, json={"deliveryMethod": "download"}
            )
            assert missing_key.status_code == 422

    async def test_ses_failure_is_502_and_records_nothing(self, client, db_session: AsyncSession):
        practice, user, sub, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)
        headers = _headers(practice)
        h, k, d = _auth_patches(_decoded(user, sub))

        with (
            h,
            k,
            d,
            patch(_P_PDF, return_value=_FAKE_PDF),
            patch(_P_SEND, AsyncMock(side_effect=RuntimeError("SES send_raw_email failed"))),
        ):
            resp = await client.post(
                f"/api/v1/patients/{patient.id}/statements",
                headers=mut(headers),
                json={"deliveryMethod": "email"},
            )
        assert resp.status_code == 502, resp.text
        assert resp.json()["error"]["code"] == "EMAIL_DELIVERY_FAILED"
        assert await _statement_rows(db_session, patient.id) == []

    async def test_other_practice_cannot_see_or_bill_patient(
        self, client, db_session: AsyncSession
    ):
        practice, _, _, patient = await _seed(db_session)
        other, other_user, other_sub, _ = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)
        headers = _headers(other)
        base = f"/api/v1/patients/{patient.id}/statements"
        h, k, d = _auth_patches(_decoded(other_user, other_sub))

        with h, k, d:
            create = await client.post(
                base, headers=mut(headers), json={"deliveryMethod": "download"}
            )
            assert create.status_code == 404
            assert create.json()["error"]["code"] == "PATIENT_NOT_FOUND"
            history = await client.get(base, headers=headers)
            assert history.status_code == 200
            assert history.json() == []
            preview = await client.get(f"{base}/preview", headers=headers)
            assert preview.status_code == 404

    async def test_feature_flag_off_is_403(self, client, db_session: AsyncSession):
        practice, user, sub, patient = await _seed(db_session, ledger_enabled=False)
        headers = _headers(practice)
        h, k, d = _auth_patches(_decoded(user, sub))

        with h, k, d:
            history = await client.get(f"/api/v1/patients/{patient.id}/statements", headers=headers)
            aging = await client.get("/api/v1/reports/patient-aging", headers=headers)
        assert history.status_code == 403
        assert history.json()["error"]["code"] == "FEATURE_NOT_ENABLED"
        assert aging.status_code == 403
