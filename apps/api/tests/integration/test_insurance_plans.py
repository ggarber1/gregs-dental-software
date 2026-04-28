"""
Integration tests for GET/POST/PATCH/DELETE /api/v1/insurance-plans.

Covers:
  - Happy path: create, list, patch, delete
  - Practice scoping: plans from another practice are invisible
  - Soft delete: deleted plans excluded from list; repeat delete is 404
  - Role auth: read_only cannot write; front_desk can
"""

from __future__ import annotations

import uuid
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from tests.integration.conftest import mut

_P_HEADER = "app.middleware.auth.jwt.get_unverified_header"
_P_KEY = "app.middleware.auth._get_public_key"
_P_DECODE = "app.middleware.auth.jwt.decode"

pytestmark = pytest.mark.integration


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _create_plan(
    client: AsyncClient,
    auth_headers: dict,
    **overrides: object,
) -> dict:
    body = {
        "carrierName": "Delta Dental",
        "payerId": "DLTADNTL",
        **overrides,
    }
    resp = await client.post(
        "/api/v1/insurance-plans",
        json=body,
        headers=mut(auth_headers),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _auth_patches(cognito_sub: str, email: str, groups: list[str]) -> ExitStack:
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


async def _make_user_with_role(db_session, practice, role: str):  # type: ignore[no-untyped-def]
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


# ── Create / List ──────────────────────────────────────────────────────────────


class TestCreateAndList:
    async def test_list_empty_before_any_plans(self, client: AsyncClient, auth_headers):
        resp = await client.get("/api/v1/insurance-plans", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_returns_201_with_fields(self, client: AsyncClient, auth_headers):
        plan = await _create_plan(client, auth_headers)
        assert plan["carrierName"] == "Delta Dental"
        assert plan["payerId"] == "DLTADNTL"
        assert plan["isInNetwork"] is True
        assert "id" in plan

    async def test_create_with_group_number(self, client: AsyncClient, auth_headers):
        plan = await _create_plan(client, auth_headers, groupNumber="GRP-001")
        assert plan["groupNumber"] == "GRP-001"

    async def test_create_out_of_network(self, client: AsyncClient, auth_headers):
        plan = await _create_plan(client, auth_headers, isInNetwork=False)
        assert plan["isInNetwork"] is False

    async def test_list_returns_created_plan(self, client: AsyncClient, auth_headers):
        await _create_plan(client, auth_headers)
        resp = await client.get("/api/v1/insurance-plans", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["carrierName"] == "Delta Dental"

    async def test_list_ordered_alphabetically(self, client: AsyncClient, auth_headers):
        await _create_plan(client, auth_headers, carrierName="MetLife", payerId="METLIF0")
        await _create_plan(client, auth_headers, carrierName="Aetna", payerId="AETNA00")
        resp = await client.get("/api/v1/insurance-plans", headers=auth_headers)
        names = [p["carrierName"] for p in resp.json()]
        assert names == sorted(names)

    async def test_create_422_missing_payer_id(self, client: AsyncClient, auth_headers):
        resp = await client.post(
            "/api/v1/insurance-plans",
            json={"carrierName": "Delta Dental"},
            headers=mut(auth_headers),
        )
        assert resp.status_code == 422


# ── Update ────────────────────────────────────────────────────────────────────


class TestUpdate:
    async def test_patch_updates_fields(self, client: AsyncClient, auth_headers):
        plan = await _create_plan(client, auth_headers)
        plan_id = plan["id"]

        resp = await client.patch(
            f"/api/v1/insurance-plans/{plan_id}",
            json={"carrierName": "Delta Dental Premier", "isInNetwork": False},
            headers=mut(auth_headers),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["carrierName"] == "Delta Dental Premier"
        assert body["isInNetwork"] is False
        assert body["payerId"] == "DLTADNTL"  # unchanged

    async def test_patch_is_partial(self, client: AsyncClient, auth_headers):
        plan = await _create_plan(client, auth_headers, groupNumber="G1")
        plan_id = plan["id"]

        resp = await client.patch(
            f"/api/v1/insurance-plans/{plan_id}",
            json={"isInNetwork": False},
            headers=mut(auth_headers),
        )
        assert resp.status_code == 200
        assert resp.json()["groupNumber"] == "G1"  # untouched

    async def test_patch_404_unknown(self, client: AsyncClient, auth_headers):
        resp = await client.patch(
            f"/api/v1/insurance-plans/{uuid.uuid4()}",
            json={"carrierName": "Cigna"},
            headers=mut(auth_headers),
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "INSURANCE_PLAN_NOT_FOUND"


# ── Delete ────────────────────────────────────────────────────────────────────


class TestDelete:
    async def test_delete_returns_204(self, client: AsyncClient, auth_headers):
        plan = await _create_plan(client, auth_headers)
        resp = await client.delete(
            f"/api/v1/insurance-plans/{plan['id']}",
            headers=mut(auth_headers),
        )
        assert resp.status_code == 204

    async def test_soft_delete_excluded_from_list(self, client: AsyncClient, auth_headers):
        plan = await _create_plan(client, auth_headers)
        await client.delete(
            f"/api/v1/insurance-plans/{plan['id']}",
            headers=mut(auth_headers),
        )
        resp = await client.get("/api/v1/insurance-plans", headers=auth_headers)
        assert resp.json() == []

    async def test_delete_twice_is_404(self, client: AsyncClient, auth_headers):
        plan = await _create_plan(client, auth_headers)
        plan_id = plan["id"]
        await client.delete(f"/api/v1/insurance-plans/{plan_id}", headers=mut(auth_headers))

        resp = await client.delete(
            f"/api/v1/insurance-plans/{plan_id}",
            headers=mut(auth_headers),
        )
        assert resp.status_code == 404

    async def test_delete_404_unknown(self, client: AsyncClient, auth_headers):
        resp = await client.delete(
            f"/api/v1/insurance-plans/{uuid.uuid4()}",
            headers=mut(auth_headers),
        )
        assert resp.status_code == 404


# ── Practice scoping ──────────────────────────────────────────────────────────


class TestPracticeScoping:
    async def test_plans_scoped_to_practice(
        self, client: AsyncClient, auth_headers, db_session
    ):
        from app.models.insurance_plan import InsurancePlan
        from app.models.practice import Practice

        other_practice = Practice(id=uuid.uuid4(), name="Other Clinic", timezone="UTC")
        db_session.add(other_practice)
        await db_session.flush()

        other_plan = InsurancePlan(
            id=uuid.uuid4(),
            practice_id=other_practice.id,
            carrier_name="Cigna",
            payer_id="CIGNA00",
            is_in_network=True,
        )
        db_session.add(other_plan)
        await db_session.commit()

        resp = await client.get("/api/v1/insurance-plans", headers=auth_headers)
        assert resp.status_code == 200
        plan_ids = [p["id"] for p in resp.json()]
        assert str(other_plan.id) not in plan_ids


# ── Role-based access ─────────────────────────────────────────────────────────


class TestRoleBasedAccess:
    async def test_read_only_can_list_plans(
        self, client: AsyncClient, auth_headers, db_session, practice
    ):
        await _create_plan(client, auth_headers)
        user, cognito_sub = await _make_user_with_role(db_session, practice, "read_only")

        with _auth_patches(cognito_sub, user.email, ["read_only"]):
            resp = await client.get(
                "/api/v1/insurance-plans",
                headers={
                    "Authorization": "Bearer test-token",
                    "X-Practice-ID": str(practice.id),
                },
            )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_read_only_cannot_create_plan(
        self, client: AsyncClient, db_session, practice
    ):
        user, cognito_sub = await _make_user_with_role(db_session, practice, "read_only")

        with _auth_patches(cognito_sub, user.email, ["read_only"]):
            resp = await client.post(
                "/api/v1/insurance-plans",
                json={"carrierName": "Aetna", "payerId": "AETNA00"},
                headers={
                    "Authorization": "Bearer test-token",
                    "X-Practice-ID": str(practice.id),
                    "Idempotency-Key": str(uuid.uuid4()),
                },
            )
        assert resp.status_code == 403

    async def test_front_desk_can_create_plan(
        self, client: AsyncClient, db_session, practice
    ):
        user, cognito_sub = await _make_user_with_role(db_session, practice, "front_desk")

        with _auth_patches(cognito_sub, user.email, ["front_desk"]):
            resp = await client.post(
                "/api/v1/insurance-plans",
                json={"carrierName": "Aetna", "payerId": "AETNA00"},
                headers={
                    "Authorization": "Bearer test-token",
                    "X-Practice-ID": str(practice.id),
                    "Idempotency-Key": str(uuid.uuid4()),
                },
            )
        assert resp.status_code == 201
