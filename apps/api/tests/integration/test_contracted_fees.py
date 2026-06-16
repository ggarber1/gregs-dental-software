"""Integration tests for /api/v1/contracted-fees (GET/PUT/DELETE)."""
from __future__ import annotations

import uuid
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import mut

pytestmark = pytest.mark.integration

_PAYER = "62308"

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


# ── Fixtures ────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def cf_practice(db_session: AsyncSession):
    """A practice with copay_estimation enabled."""
    from app.models.practice import Practice

    p = Practice(
        id=uuid.uuid4(),
        name="Contracted Dental",
        timezone="America/Chicago",
        features={"copay_estimation": True},
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest_asyncio.fixture
async def cf_staff_user(db_session: AsyncSession, cf_practice):
    """Admin user for cf_practice."""
    from app.models.user import PracticeUser, User

    cognito_sub = f"cf-sub-{uuid.uuid4().hex}"
    user = User(
        id=uuid.uuid4(),
        cognito_sub=cognito_sub,
        email=f"cf-staff-{uuid.uuid4().hex[:6]}@test.local",
        full_name="CF Staff",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    pu = PracticeUser(
        practice_id=cf_practice.id,
        user_id=user.id,
        role="admin",
        is_active=True,
    )
    db_session.add(pu)
    await db_session.commit()
    return user, cognito_sub


@pytest_asyncio.fixture
async def cf_auth_headers(cf_practice, cf_staff_user):
    """Auth headers scoped to cf_practice with copay_estimation on."""
    user, cognito_sub = cf_staff_user
    with (
        patch(_P_HEADER, return_value={"kid": "test-kid"}),
        patch(_P_KEY, new=AsyncMock(return_value="fake-public-key")),
        patch(
            _P_DECODE,
            return_value={
                "sub": cognito_sub,
                "email": user.email,
                "cognito:groups": ["admin"],
            },
        ),
    ):
        yield {
            "Authorization": "Bearer test-token",
            "X-Practice-ID": str(cf_practice.id),
        }


# ── Tests ────────────────────────────────────────────────────────────────────────


class TestListContractedFees:
    async def test_get_lists_catalog_with_blank_fees(
        self, client: AsyncClient, cf_auth_headers: dict
    ):
        resp = await client.get(
            "/api/v1/contracted-fees",
            params={"payer_id": _PAYER},
            headers=cf_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert rows, "Expected at least one CDT code in catalog"
        assert all(r["allowedAmountCents"] is None for r in rows)
        assert all(r["notCovered"] is False for r in rows)
        assert all(r["requiresPriorAuth"] is False for r in rows)
        assert all(r["payerId"] == _PAYER for r in rows)

    async def test_get_without_feature_returns_403(
        self, client: AsyncClient, auth_headers: dict
    ):
        # The shared practice fixture has no copay_estimation feature.
        resp = await client.get(
            "/api/v1/contracted-fees",
            params={"payer_id": _PAYER},
            headers=auth_headers,
        )
        assert resp.status_code == 403, resp.text


class TestSetContractedFee:
    async def test_put_then_get_reflects_allowed_amount(
        self, client: AsyncClient, cf_auth_headers: dict
    ):
        rows = (
            await client.get(
                "/api/v1/contracted-fees",
                params={"payer_id": _PAYER},
                headers=cf_auth_headers,
            )
        ).json()
        code_id = rows[0]["cdtCodeId"]

        put = await client.put(
            f"/api/v1/contracted-fees/{code_id}",
            params={"payer_id": _PAYER},
            json={"allowedAmountCents": 8000, "notCovered": False},
            headers=mut(cf_auth_headers),
        )
        assert put.status_code == 200, put.text
        body = put.json()
        assert body["allowedAmountCents"] == 8000
        assert body["notCovered"] is False
        assert body["cdtCodeId"] == code_id

        get_after = await client.get(
            "/api/v1/contracted-fees",
            params={"payer_id": _PAYER},
            headers=cf_auth_headers,
        )
        assert get_after.status_code == 200, get_after.text
        updated = next(r for r in get_after.json() if r["cdtCodeId"] == code_id)
        assert updated["allowedAmountCents"] == 8000

    async def test_put_twice_updates_in_place(
        self, client: AsyncClient, cf_auth_headers: dict
    ):
        rows = (
            await client.get(
                "/api/v1/contracted-fees",
                params={"payer_id": _PAYER},
                headers=cf_auth_headers,
            )
        ).json()
        code_id = rows[0]["cdtCodeId"]
        await client.put(
            f"/api/v1/contracted-fees/{code_id}",
            params={"payer_id": _PAYER},
            json={"allowedAmountCents": 5000},
            headers=mut(cf_auth_headers),
        )
        put2 = await client.put(
            f"/api/v1/contracted-fees/{code_id}",
            params={"payer_id": _PAYER},
            json={"allowedAmountCents": 7500, "notCovered": True},
            headers=mut(cf_auth_headers),
        )
        assert put2.status_code == 200, put2.text
        assert put2.json()["allowedAmountCents"] == 7500
        assert put2.json()["notCovered"] is True

    async def test_put_unknown_code_404(
        self, client: AsyncClient, cf_auth_headers: dict
    ):
        resp = await client.put(
            f"/api/v1/contracted-fees/{uuid.uuid4()}",
            params={"payer_id": _PAYER},
            json={"allowedAmountCents": 100},
            headers=mut(cf_auth_headers),
        )
        assert resp.status_code == 404, resp.text

    async def test_put_null_allowed_amount_is_valid(
        self, client: AsyncClient, cf_auth_headers: dict
    ):
        rows = (
            await client.get(
                "/api/v1/contracted-fees",
                params={"payer_id": _PAYER},
                headers=cf_auth_headers,
            )
        ).json()
        code_id = rows[0]["cdtCodeId"]
        put = await client.put(
            f"/api/v1/contracted-fees/{code_id}",
            params={"payer_id": _PAYER},
            json={"allowedAmountCents": None, "notCovered": True},
            headers=mut(cf_auth_headers),
        )
        assert put.status_code == 200, put.text
        assert put.json()["allowedAmountCents"] is None
        assert put.json()["notCovered"] is True


class TestRevertContractedFee:
    async def test_delete_reverts_to_null(
        self, client: AsyncClient, cf_auth_headers: dict
    ):
        rows = (
            await client.get(
                "/api/v1/contracted-fees",
                params={"payer_id": _PAYER},
                headers=cf_auth_headers,
            )
        ).json()
        code_id = rows[0]["cdtCodeId"]
        await client.put(
            f"/api/v1/contracted-fees/{code_id}",
            params={"payer_id": _PAYER},
            json={"allowedAmountCents": 5000},
            headers=mut(cf_auth_headers),
        )
        d = await client.delete(
            f"/api/v1/contracted-fees/{code_id}",
            params={"payer_id": _PAYER},
            headers=mut(cf_auth_headers),
        )
        assert d.status_code == 204, d.text

        rows2 = (
            await client.get(
                "/api/v1/contracted-fees",
                params={"payer_id": _PAYER},
                headers=cf_auth_headers,
            )
        ).json()
        reverted = next(r for r in rows2 if r["cdtCodeId"] == code_id)
        assert reverted["allowedAmountCents"] is None

    async def test_delete_non_set_code_is_noop_204(
        self, client: AsyncClient, cf_auth_headers: dict
    ):
        rows = (
            await client.get(
                "/api/v1/contracted-fees",
                params={"payer_id": _PAYER},
                headers=cf_auth_headers,
            )
        ).json()
        code_id = rows[0]["cdtCodeId"]
        resp = await client.delete(
            f"/api/v1/contracted-fees/{code_id}",
            params={"payer_id": _PAYER},
            headers=mut(cf_auth_headers),
        )
        assert resp.status_code == 204, resp.text

    async def test_revert_then_reset_creates_new_row(
        self, client: AsyncClient, cf_auth_headers: dict, db_session: AsyncSession
    ):
        from sqlalchemy import func, select

        from app.models.contracted_fee_schedule import ContractedFeeSchedule

        rows = (
            await client.get(
                "/api/v1/contracted-fees",
                params={"payer_id": _PAYER},
                headers=cf_auth_headers,
            )
        ).json()
        code_id = rows[0]["cdtCodeId"]
        await client.put(
            f"/api/v1/contracted-fees/{code_id}",
            params={"payer_id": _PAYER},
            json={"allowedAmountCents": 4000},
            headers=mut(cf_auth_headers),
        )
        await client.delete(
            f"/api/v1/contracted-fees/{code_id}",
            params={"payer_id": _PAYER},
            headers=mut(cf_auth_headers),
        )
        reset = await client.put(
            f"/api/v1/contracted-fees/{code_id}",
            params={"payer_id": _PAYER},
            json={"allowedAmountCents": 6000},
            headers=mut(cf_auth_headers),
        )
        assert reset.status_code == 200, reset.text
        assert reset.json()["allowedAmountCents"] == 6000

        # Only one active row should exist for this code+payer combo.
        cf_practice_id = uuid.UUID(cf_auth_headers["X-Practice-ID"])
        active = await db_session.scalar(
            select(func.count())
            .select_from(ContractedFeeSchedule)
            .where(
                ContractedFeeSchedule.deleted_at.is_(None),
                ContractedFeeSchedule.practice_id == cf_practice_id,
                ContractedFeeSchedule.payer_id == _PAYER,
                ContractedFeeSchedule.cdt_code_id == uuid.UUID(code_id),
            )
        )
        assert active == 1


class TestPracticeIsolation:
    async def test_other_practice_sees_empty_fees(
        self, client: AsyncClient, cf_auth_headers: dict, db_session: AsyncSession
    ):
        rows = (
            await client.get(
                "/api/v1/contracted-fees",
                params={"payer_id": _PAYER},
                headers=cf_auth_headers,
            )
        ).json()
        code_id = rows[0]["cdtCodeId"]
        await client.put(
            f"/api/v1/contracted-fees/{code_id}",
            params={"payer_id": _PAYER},
            json={"allowedAmountCents": 9000},
            headers=mut(cf_auth_headers),
        )

        from app.models.practice import Practice
        from app.models.user import PracticeUser, User

        other = Practice(
            id=uuid.uuid4(),
            name="Other Dental",
            timezone="America/New_York",
            features={"copay_estimation": True},
        )
        db_session.add(other)
        await db_session.commit()

        sub = f"other-sub-{uuid.uuid4().hex}"
        user = User(
            id=uuid.uuid4(),
            cognito_sub=sub,
            email=f"other-{uuid.uuid4().hex[:6]}@test.local",
            full_name="Other Staff",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()
        db_session.add(
            PracticeUser(practice_id=other.id, user_id=user.id, role="admin", is_active=True)
        )
        await db_session.commit()

        with _auth_patches(sub, user.email, ["admin"]):
            other_headers = {
                "Authorization": "Bearer t",
                "X-Practice-ID": str(other.id),
            }
            other_rows = (
                await client.get(
                    "/api/v1/contracted-fees",
                    params={"payer_id": _PAYER},
                    headers=other_headers,
                )
            ).json()
        target = next(r for r in other_rows if r["cdtCodeId"] == code_id)
        assert target["allowedAmountCents"] is None


class TestRoleAuth:
    async def test_read_only_cannot_set_fee(
        self, client: AsyncClient, cf_practice, db_session: AsyncSession
    ):
        from app.models.user import PracticeUser, User

        sub = f"ro-sub-{uuid.uuid4().hex}"
        user = User(
            id=uuid.uuid4(),
            cognito_sub=sub,
            email=f"ro-{uuid.uuid4().hex[:6]}@test.local",
            full_name="Read Only",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()
        db_session.add(
            PracticeUser(
                practice_id=cf_practice.id, user_id=user.id, role="read_only", is_active=True
            )
        )
        await db_session.commit()

        # Need a CDT code ID; pull from list using admin headers first.
        admin_sub = f"admin-sub-{uuid.uuid4().hex}"
        admin_user = User(
            id=uuid.uuid4(),
            cognito_sub=admin_sub,
            email=f"admin-{uuid.uuid4().hex[:6]}@test.local",
            full_name="Admin",
            is_active=True,
        )
        db_session.add(admin_user)
        await db_session.flush()
        db_session.add(
            PracticeUser(
                practice_id=cf_practice.id,
                user_id=admin_user.id,
                role="admin",
                is_active=True,
            )
        )
        await db_session.commit()

        with _auth_patches(admin_sub, admin_user.email, ["admin"]):
            admin_headers = {
                "Authorization": "Bearer t",
                "X-Practice-ID": str(cf_practice.id),
            }
            rows = (
                await client.get(
                    "/api/v1/contracted-fees",
                    params={"payer_id": _PAYER},
                    headers=admin_headers,
                )
            ).json()
        code_id = rows[0]["cdtCodeId"]

        with _auth_patches(sub, user.email, ["read_only"]):
            ro_headers = {
                "Authorization": "Bearer t",
                "X-Practice-ID": str(cf_practice.id),
            }
            resp = await client.put(
                f"/api/v1/contracted-fees/{code_id}",
                params={"payer_id": _PAYER},
                json={"allowedAmountCents": 4500},
                headers=mut(ro_headers),
            )
        assert resp.status_code == 403, resp.text
