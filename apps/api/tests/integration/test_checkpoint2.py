"""
Staging Checkpoint 2 verification tests — End of Module 2 (after 2.1–2.4).

These tests encode the specific security properties that must hold before
Checkpoint 2 can be signed off:

  1. SSN is stored as encrypted BYTEA, not plaintext.
  2. Every patient create and read produces an audit_logs row.

Run with:
    pytest -m integration tests/integration/test_checkpoint2.py
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import mut

pytestmark = pytest.mark.integration

_PATIENT_BODY = {
    "firstName": "Checkpoint",
    "lastName": "Two",
    "dateOfBirth": "1975-03-10",
    "sex": "female",
    "phone": "+15550009999",
    "email": "checkpoint2@test.internal",
    "addressLine1": "99 Security Blvd",
    "city": "Boston",
    "state": "MA",
    "zip": "02101",
    "allergies": [],
    "medicalAlerts": [],
    "smsOptOut": False,
}


# ── 1. SSN encrypted at rest ───────────────────────────────────────────────────


class TestSSNEncryptedAtRest:
    """SSN (last-four) must be stored as AES-256-GCM encrypted BYTEA, never plaintext."""

    async def test_ssn_stored_as_bytea_not_plaintext(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession
    ):
        body = {**_PATIENT_BODY, "ssnLastFour": "7890"}
        resp = await client.post(
            "/api/v1/patients", json=body, headers=mut(auth_headers)
        )
        assert resp.status_code == 201
        patient_id = resp.json()["id"]

        # Query the raw column — bytea comes back as memoryview or bytes from asyncpg.
        result = await db_session.execute(
            text("SELECT ssn_encrypted FROM patients WHERE id = CAST(:id AS uuid)"),
            {"id": patient_id},
        )
        row = result.fetchone()
        assert row is not None, "Patient row not found in DB"

        raw = bytes(row[0])
        assert len(raw) > 0, "ssn_encrypted must not be empty"
        assert b"7890" not in raw, (
            "SSN must not appear as plaintext inside the stored bytes"
        )

    async def test_ssn_decrypts_to_original_value(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession
    ):
        body = {**_PATIENT_BODY, "ssnLastFour": "4321"}
        resp = await client.post(
            "/api/v1/patients", json=body, headers=mut(auth_headers)
        )
        assert resp.status_code == 201
        patient_id = resp.json()["id"]

        result = await db_session.execute(
            text("SELECT ssn_encrypted FROM patients WHERE id = CAST(:id AS uuid)"),
            {"id": patient_id},
        )
        raw = bytes(result.fetchone()[0])

        from app.core.encryption import decrypt

        assert decrypt(raw) == "4321", "Decrypted value must match the original SSN"

    async def test_ssn_null_when_not_provided(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession
    ):
        resp = await client.post(
            "/api/v1/patients", json=_PATIENT_BODY, headers=mut(auth_headers)
        )
        assert resp.status_code == 201
        patient_id = resp.json()["id"]

        result = await db_session.execute(
            text("SELECT ssn_encrypted FROM patients WHERE id = CAST(:id AS uuid)"),
            {"id": patient_id},
        )
        row = result.fetchone()
        assert row[0] is None, "ssn_encrypted must be NULL when no SSN was provided"

    async def test_two_encryptions_of_same_ssn_differ(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession
    ):
        """AES-GCM uses a random nonce — the same SSN encrypted twice must not
        produce the same ciphertext."""
        body = {**_PATIENT_BODY, "ssnLastFour": "1111"}

        resp1 = await client.post(
            "/api/v1/patients", json=body, headers=mut(auth_headers)
        )
        resp2 = await client.post(
            "/api/v1/patients",
            json={**body, "email": "checkpoint2b@test.internal"},
            headers=mut(auth_headers),
        )
        assert resp1.status_code == 201
        assert resp2.status_code == 201

        ids = [resp1.json()["id"], resp2.json()["id"]]
        result = await db_session.execute(
            text(
                "SELECT ssn_encrypted FROM patients WHERE id = ANY(CAST(:ids AS uuid[]))"
            ),
            {"ids": ids},
        )
        blobs = [bytes(r[0]) for r in result.fetchall()]
        assert len(blobs) == 2
        assert blobs[0] != blobs[1], (
            "Random nonce must ensure identical SSNs produce different ciphertext"
        )


# ── 2. Audit log coverage ──────────────────────────────────────────────────────


class TestAuditLogCoverage:
    """
    Every authenticated patient create and read must produce an audit_logs row.

    The middleware writes fire-and-forget via asyncio.create_task.  We yield
    briefly to the event loop after each request so the background write can
    commit before we assert.
    """

    async def _flush_audit_tasks(self) -> None:
        """Yield to the event loop enough times for the background audit write
        to open a DB session, commit, and close."""
        await asyncio.sleep(0.1)

    async def test_patient_create_writes_audit_log(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, practice
    ):
        from app.models.audit_log import AuditLog

        resp = await client.post(
            "/api/v1/patients", json=_PATIENT_BODY, headers=mut(auth_headers)
        )
        assert resp.status_code == 201
        patient_id = resp.json()["id"]

        await self._flush_audit_tasks()

        rows = (
            await db_session.scalars(
                select(AuditLog).where(
                    AuditLog.practice_id == practice.id,
                    AuditLog.action == "POST",
                    AuditLog.resource_type == "patients",
                    AuditLog.status_code == 201,
                )
            )
        ).all()

        assert len(rows) >= 1, (
            "An audit_logs row must be written for every patient create (POST 201)"
        )

    async def test_patient_read_writes_audit_log(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, practice
    ):
        from app.models.audit_log import AuditLog

        create = await client.post(
            "/api/v1/patients", json=_PATIENT_BODY, headers=mut(auth_headers)
        )
        assert create.status_code == 201
        patient_id = create.json()["id"]

        # Read
        get_resp = await client.get(
            f"/api/v1/patients/{patient_id}", headers=auth_headers
        )
        assert get_resp.status_code == 200

        await self._flush_audit_tasks()

        rows = (
            await db_session.scalars(
                select(AuditLog).where(
                    AuditLog.practice_id == practice.id,
                    AuditLog.action == "GET",
                    AuditLog.resource_type == "patients",
                    AuditLog.resource_id == patient_id,
                    AuditLog.status_code == 200,
                )
            )
        ).all()

        assert len(rows) >= 1, (
            "An audit_logs row must be written for every patient read (GET 200)"
        )

    async def test_patient_update_writes_audit_log(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, practice
    ):
        from app.models.audit_log import AuditLog

        create = await client.post(
            "/api/v1/patients", json=_PATIENT_BODY, headers=mut(auth_headers)
        )
        patient_id = create.json()["id"]

        await client.patch(
            f"/api/v1/patients/{patient_id}",
            json={"city": "Cambridge"},
            headers=mut(auth_headers),
        )

        await self._flush_audit_tasks()

        rows = (
            await db_session.scalars(
                select(AuditLog).where(
                    AuditLog.practice_id == practice.id,
                    AuditLog.action == "PATCH",
                    AuditLog.resource_type == "patients",
                    AuditLog.resource_id == patient_id,
                )
            )
        ).all()

        assert len(rows) >= 1, (
            "An audit_logs row must be written for every patient update (PATCH)"
        )

    async def test_audit_log_captures_practice_and_user(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, practice, staff_user
    ):
        """Each audit row must include practice_id and user_id for correlating access."""
        from app.models.audit_log import AuditLog

        user, cognito_sub = staff_user

        await client.post(
            "/api/v1/patients", json=_PATIENT_BODY, headers=mut(auth_headers)
        )

        await self._flush_audit_tasks()

        row = (
            await db_session.scalars(
                select(AuditLog).where(
                    AuditLog.practice_id == practice.id,
                    AuditLog.action == "POST",
                    AuditLog.resource_type == "patients",
                )
            )
        ).first()

        assert row is not None, "Audit log row not found"
        assert row.practice_id == practice.id, "Audit log must record practice_id"
        assert row.user_id == cognito_sub, "Audit log must record the authenticated user's sub"
