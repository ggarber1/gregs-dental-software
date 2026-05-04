"""
Integration tests for the treatment plan flow.

Requires a running Postgres at localhost:5432 (dental/dental) and Redis at localhost:6379.
Run with: pytest -m integration
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import mut


@pytest_asyncio.fixture
async def treatment_patient(db_session: AsyncSession, practice):
    from app.models.patient import Patient

    p = Patient(
        id=uuid.uuid4(),
        practice_id=practice.id,
        first_name="Treatment",
        last_name="Testpatient",
        date_of_birth=date(1985, 7, 20),
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_treatment_plan_flow(
    client: AsyncClient,
    auth_headers: dict,
    treatment_patient,
    db_session: AsyncSession,
):
    patient_id = str(treatment_patient.id)
    base_url = f"/api/v1/patients/{patient_id}/treatment-plans"

    # ── 1. List plans: empty for new patient ──────────────────────────────────
    response = await client.get(base_url, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["items"] == []

    # ── 2. Create plan with 3 items ───────────────────────────────────────────
    payload = {
        "name": "Phase 1 — Restorations",
        "items": [
            {"procedureCode": "D2391", "procedureName": "Resin composite #14",
             "feeCents": 25000, "toothNumber": "14"},
            {"procedureCode": "D2391", "procedureName": "Resin composite #18",
             "feeCents": 25000, "toothNumber": "18"},
            {"procedureCode": "D2750", "procedureName": "Crown #30",
             "feeCents": 150000, "toothNumber": "30"},
        ],
    }
    response = await client.post(base_url, json=payload, headers=mut(auth_headers))
    assert response.status_code == 201, response.text
    plan = response.json()
    plan_id = plan["id"]
    assert plan["status"] == "proposed"
    assert plan["name"] == "Phase 1 — Restorations"
    assert len(plan["items"]) == 3

    # ── 3. Get plan detail ────────────────────────────────────────────────────
    response = await client.get(f"{base_url}/{plan_id}", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()["items"]) == 3

    # ── 4. Accept the plan ────────────────────────────────────────────────────
    response = await client.patch(
        f"{base_url}/{plan_id}",
        json={"status": "accepted"},
        headers=mut(auth_headers),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["acceptedAt"] is not None

    # ── 5. Invalid transition: accepted → proposed → 409 ─────────────────────
    response = await client.patch(
        f"{base_url}/{plan_id}",
        json={"status": "proposed"},
        headers=mut(auth_headers),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"

    # ── 6. Schedule item 1 → plan auto-transitions to in_progress ─────────────
    item_id = plan["items"][0]["id"]
    response = await client.patch(
        f"{base_url}/{plan_id}/items/{item_id}",
        json={"status": "accepted"},
        headers=mut(auth_headers),
    )
    assert response.status_code == 200

    response = await client.patch(
        f"{base_url}/{plan_id}/items/{item_id}",
        json={"status": "scheduled"},
        headers=mut(auth_headers),
    )
    assert response.status_code == 200

    response = await client.get(f"{base_url}/{plan_id}", headers=auth_headers)
    assert response.json()["status"] == "in_progress"

    # ── 7. Complete item 1 ────────────────────────────────────────────────────
    response = await client.patch(
        f"{base_url}/{plan_id}/items/{item_id}",
        json={"status": "completed"},
        headers=mut(auth_headers),
    )
    assert response.status_code == 200

    # Plan should still be in_progress (2 items still proposed)
    response = await client.get(f"{base_url}/{plan_id}", headers=auth_headers)
    assert response.json()["status"] == "in_progress"

    # ── 8. Refuse remaining two items → plan auto-transitions to completed ────
    remaining_items = [i for i in response.json()["items"] if i["id"] != item_id]
    for it in remaining_items:
        response = await client.patch(
            f"{base_url}/{plan_id}/items/{it['id']}",
            json={"status": "refused"},
            headers=mut(auth_headers),
        )
        assert response.status_code == 200

    response = await client.get(f"{base_url}/{plan_id}", headers=auth_headers)
    assert response.json()["status"] == "completed"
    assert response.json()["completedAt"] is not None

    # ── 9. Add a new item after completion ────────────────────────────────────
    response = await client.post(
        f"{base_url}/{plan_id}/items",
        json={"procedureCode": "D4341", "procedureName": "SRP — quadrant 1", "feeCents": 30000},
        headers=mut(auth_headers),
    )
    assert response.status_code == 201

    # ── 10. Delete the new item ───────────────────────────────────────────────
    new_item_id = response.json()["id"]
    response = await client.delete(
        f"{base_url}/{plan_id}/items/{new_item_id}",
        headers=mut(auth_headers),
    )
    assert response.status_code == 204

    # Item should be gone from detail
    response = await client.get(f"{base_url}/{plan_id}", headers=auth_headers)
    item_ids = [i["id"] for i in response.json()["items"]]
    assert new_item_id not in item_ids

    # ── 11. Auth: Practice B cannot access this plan ──────────────────────────
    practice_b_headers = {**auth_headers, "X-Practice-ID": str(uuid.uuid4())}
    response = await client.get(f"{base_url}/{plan_id}", headers=practice_b_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.integration
async def test_open_plan_queue(
    client: AsyncClient,
    auth_headers: dict,
    treatment_patient,
):
    patient_id = str(treatment_patient.id)
    base_url = f"/api/v1/patients/{patient_id}/treatment-plans"

    # ── 1. Open queue starts empty ────────────────────────────────────────────
    response = await client.get("/api/v1/treatment-plans/open", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []

    # ── 2. Create and accept a plan with unscheduled items ────────────────────
    payload = {
        "name": "Pending Plan",
        "items": [
            {"procedureCode": "D2391", "procedureName": "Filling", "feeCents": 20000},
        ],
    }
    response = await client.post(base_url, json=payload, headers=mut(auth_headers))
    assert response.status_code == 201
    plan_id = response.json()["id"]

    response = await client.patch(
        f"{base_url}/{plan_id}",
        json={"status": "accepted"},
        headers=mut(auth_headers),
    )
    assert response.status_code == 200

    # ── 3. Patient now appears in open queue ──────────────────────────────────
    response = await client.get("/api/v1/treatment-plans/open", headers=auth_headers)
    assert response.status_code == 200
    queue = response.json()
    assert len(queue) == 1
    assert queue[0]["patientId"] == patient_id
    assert queue[0]["planName"] == "Pending Plan"
    assert queue[0]["pendingItemCount"] == 1

    # ── 4. Schedule the item → disappears from open queue ────────────────────
    detail = await client.get(f"{base_url}/{plan_id}", headers=auth_headers)
    item_id = detail.json()["items"][0]["id"]

    await client.patch(
        f"{base_url}/{plan_id}/items/{item_id}",
        json={"status": "accepted"},
        headers=mut(auth_headers),
    )
    await client.patch(
        f"{base_url}/{plan_id}/items/{item_id}",
        json={"status": "scheduled"},
        headers=mut(auth_headers),
    )

    response = await client.get("/api/v1/treatment-plans/open", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
@pytest.mark.integration
async def test_plan_list_pagination(
    client: AsyncClient,
    auth_headers: dict,
    treatment_patient,
):
    patient_id = str(treatment_patient.id)
    base_url = f"/api/v1/patients/{patient_id}/treatment-plans"

    # Create 5 plans
    for i in range(5):
        response = await client.post(
            base_url,
            json={"name": f"Plan {i + 1}"},
            headers=mut(auth_headers),
        )
        assert response.status_code == 201

    # Fetch first page of 3
    response = await client.get(f"{base_url}?limit=3", headers=auth_headers)
    assert response.status_code == 200
    page1 = response.json()
    assert len(page1["items"]) == 3
    assert page1["hasMore"] is True
    cursor = page1["nextCursor"]

    # Fetch second page using cursor
    response = await client.get(f"{base_url}?limit=3&cursor={cursor}", headers=auth_headers)
    assert response.status_code == 200
    page2 = response.json()
    assert len(page2["items"]) == 2
    assert page2["hasMore"] is False

    # No duplicates between pages
    ids_page1 = {i["id"] for i in page1["items"]}
    ids_page2 = {i["id"] for i in page2["items"]}
    assert ids_page1.isdisjoint(ids_page2)
