"""
Integration test for the full medical history versioning flow.

Requires a running Postgres at localhost:5432 (dental/dental).
Run with: pytest -m integration
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import mut


@pytest_asyncio.fixture
async def patient_with_no_history(db_session: AsyncSession, practice):
    from datetime import date

    from app.models.patient import Patient

    p = Patient(
        id=uuid.uuid4(),
        practice_id=practice.id,
        first_name="Medical",
        last_name="Testpatient",
        date_of_birth=date(1980, 3, 10),
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_medical_history_flow(
    client: AsyncClient,
    auth_headers: dict,
    patient_with_no_history,
    db_session: AsyncSession,
):
    from app.models.medical_history_version import MedicalHistoryVersion

    patient_id = str(patient_with_no_history.id)
    base_url = f"/api/v1/patients/{patient_id}/medical-history"

    # ── 1. GET latest: expect 404 (no history yet) ─────────────────────────────
    response = await client.get(base_url, headers=auth_headers)
    assert response.status_code == 404

    # ── 2. POST initial history ────────────────────────────────────────────────
    payload = {
        "allergies": [{"name": "penicillin", "severity": "moderate"}],
        "medications": [{"name": "metformin", "dose": "500mg", "frequency": "twice daily"}],
        "conditions": [{"name": "diabetes", "icd10Hint": "E11.9"}],
        "additionalNotes": "Patient reports well-controlled diabetes.",
    }
    response = await client.post(base_url, json=payload, headers=mut(auth_headers))
    assert response.status_code == 201, response.text
    v1 = response.json()
    assert v1["versionNumber"] == 1
    assert v1["flags"]["flagDiabetes"] is True  # "diabetes" triggers the flag
    assert v1["allergies"][0]["name"] == "penicillin"
    assert v1["medications"][0]["name"] == "metformin"
    assert v1["additionalNotes"] == "Patient reports well-controlled diabetes."

    # ── 3. Verify Patient flat arrays updated ──────────────────────────────────
    await db_session.refresh(patient_with_no_history)
    assert "penicillin" in patient_with_no_history.allergies
    assert "metformin" in patient_with_no_history.medications
    assert "diabetes" in patient_with_no_history.medical_alerts

    # ── 4. GET latest: returns version 1 ──────────────────────────────────────
    response = await client.get(base_url, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["versionNumber"] == 1

    # ── 5. POST updated history ────────────────────────────────────────────────
    payload_v2 = {
        "allergies": [
            {"name": "penicillin", "severity": "moderate"},
            {"name": "latex", "severity": "severe"},
        ],
        "medications": [{"name": "warfarin", "dose": "5mg"}],
        "conditions": [{"name": "diabetes"}, {"name": "atrial fibrillation"}],
    }
    response = await client.post(base_url, json=payload_v2, headers=mut(auth_headers))
    assert response.status_code == 201
    v2 = response.json()
    assert v2["versionNumber"] == 2
    assert v2["flags"]["flagBloodThinners"] is True   # "warfarin"
    assert v2["flags"]["flagLatexAllergy"] is True    # "latex" allergy
    assert v2["flags"]["flagHeartCondition"] is True  # "atrial fibrillation"

    # ── 6. GET latest: now returns version 2 ──────────────────────────────────
    response = await client.get(base_url, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["versionNumber"] == 2

    # ── 7. GET history: two versions, descending order ─────────────────────────
    response = await client.get(f"{base_url}/history", headers=auth_headers)
    assert response.status_code == 200
    history = response.json()
    assert history["total"] == 2
    assert history["items"][0]["versionNumber"] == 2
    assert history["items"][1]["versionNumber"] == 1

    # ── 8. GET specific version: v1 snapshot is intact ────────────────────────
    v1_id = v1["id"]
    response = await client.get(f"{base_url}/{v1_id}", headers=auth_headers)
    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["versionNumber"] == 1
    assert snapshot["allergies"][0]["name"] == "penicillin"
    assert len(snapshot["allergies"]) == 1  # v1 only had 1 allergy

    # ── 9. Flat arrays reflect latest version (v2) ─────────────────────────────
    await db_session.refresh(patient_with_no_history)
    assert "warfarin" in patient_with_no_history.medications
    assert "latex" in patient_with_no_history.allergies

    # ── 10. Version rows exist in DB ───────────────────────────────────────────
    rows = (
        await db_session.scalars(
            select(MedicalHistoryVersion).where(
                MedicalHistoryVersion.patient_id == patient_with_no_history.id
            )
        )
    ).all()
    assert len(rows) == 2
