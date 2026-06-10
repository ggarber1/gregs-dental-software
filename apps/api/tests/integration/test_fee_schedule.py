"""Integration tests for GET/PUT/DELETE /api/v1/fee-schedule.

Covers:
  - GET returns the full CDT catalog joined with the practice's overrides
  - PUT upserts a fee; GET then reflects it as practiceFeeCents + resolvedFeeCents
  - PUT unknown code -> 404
  - DELETE reverts (practiceFeeCents null, resolvedFeeCents falls back to default)
  - DELETE on a non-overridden code -> 204 no-op
  - Practice isolation: practice A's override invisible to practice B
  - Role auth: read_only cannot write
"""

from __future__ import annotations

import uuid
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import mut

pytestmark = pytest.mark.integration

_P_HEADER = "app.middleware.auth.jwt.get_unverified_header"
_P_KEY = "app.middleware.auth._get_public_key"
_P_DECODE = "app.middleware.auth.jwt.decode"


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


async def _make_user_with_role(db_session: AsyncSession, practice, role: str):  # type: ignore[no-untyped-def]
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
    pu = PracticeUser(practice_id=practice.id, user_id=user.id, role=role, is_active=True)
    db_session.add(pu)
    await db_session.commit()
    return user, cognito_sub


def _find(rows: list[dict], code: str) -> dict:
    return next(r for r in rows if r["code"] == code)


class TestGetFeeSchedule:
    async def test_get_lists_full_catalog_with_blank_fees(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.get("/api/v1/fee-schedule", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        codes = [r["code"] for r in rows]
        assert "D0120" in codes and "D1110" in codes
        d0120 = _find(rows, "D0120")
        assert d0120["practiceFeeCents"] is None
        assert d0120["resolvedFeeCents"] == d0120["defaultFeeCents"]


class TestSetFee:
    async def test_put_sets_fee_then_get_reflects_it(
        self, client: AsyncClient, auth_headers
    ):
        put = await client.put(
            "/api/v1/fee-schedule/D0120",
            json={"feeCents": 4500},
            headers=mut(auth_headers),
        )
        assert put.status_code == 200, put.text
        assert put.json()["practiceFeeCents"] == 4500
        assert put.json()["resolvedFeeCents"] == 4500

        rows = (await client.get("/api/v1/fee-schedule", headers=auth_headers)).json()
        d0120 = _find(rows, "D0120")
        assert d0120["practiceFeeCents"] == 4500
        assert d0120["resolvedFeeCents"] == 4500

    async def test_put_twice_updates_in_place(self, client: AsyncClient, auth_headers):
        await client.put(
            "/api/v1/fee-schedule/D0120", json={"feeCents": 4500}, headers=mut(auth_headers)
        )
        await client.put(
            "/api/v1/fee-schedule/D0120", json={"feeCents": 5000}, headers=mut(auth_headers)
        )
        rows = (await client.get("/api/v1/fee-schedule", headers=auth_headers)).json()
        assert _find(rows, "D0120")["practiceFeeCents"] == 5000

    async def test_put_unknown_code_404(self, client: AsyncClient, auth_headers):
        resp = await client.put(
            "/api/v1/fee-schedule/D9999", json={"feeCents": 100}, headers=mut(auth_headers)
        )
        assert resp.status_code == 404, resp.text


class TestRevertFee:
    async def test_delete_reverts_to_default(self, client: AsyncClient, auth_headers):
        await client.put(
            "/api/v1/fee-schedule/D0120", json={"feeCents": 4500}, headers=mut(auth_headers)
        )
        delete = await client.delete("/api/v1/fee-schedule/D0120", headers=mut(auth_headers))
        assert delete.status_code == 204, delete.text

        rows = (await client.get("/api/v1/fee-schedule", headers=auth_headers)).json()
        d0120 = _find(rows, "D0120")
        assert d0120["practiceFeeCents"] is None
        assert d0120["resolvedFeeCents"] == d0120["defaultFeeCents"]

    async def test_delete_non_overridden_is_noop_204(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.delete("/api/v1/fee-schedule/D0120", headers=mut(auth_headers))
        assert resp.status_code == 204, resp.text


class TestPracticeIsolation:
    async def test_other_practice_override_invisible(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession
    ):
        await client.put(
            "/api/v1/fee-schedule/D0120", json={"feeCents": 4500}, headers=mut(auth_headers)
        )
        from app.models.practice import Practice

        other = Practice(id=uuid.uuid4(), name="Other Dental", timezone="America/New_York")
        db_session.add(other)
        await db_session.commit()
        user, sub = await _make_user_with_role(db_session, other, "admin")
        with _auth_patches(sub, user.email, ["admin"]):
            headers = {"Authorization": "Bearer t", "X-Practice-ID": str(other.id)}
            rows = (await client.get("/api/v1/fee-schedule", headers=headers)).json()
        assert _find(rows, "D0120")["practiceFeeCents"] is None


class TestRoleAuth:
    async def test_read_only_cannot_set_fee(
        self, client: AsyncClient, practice, db_session: AsyncSession
    ):
        user, sub = await _make_user_with_role(db_session, practice, "read_only")
        with _auth_patches(sub, user.email, ["read_only"]):
            headers = {"Authorization": "Bearer t", "X-Practice-ID": str(practice.id)}
            resp = await client.put(
                "/api/v1/fee-schedule/D0120", json={"feeCents": 4500}, headers=mut(headers)
            )
        assert resp.status_code == 403, resp.text
