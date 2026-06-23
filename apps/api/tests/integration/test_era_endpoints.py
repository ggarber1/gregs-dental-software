"""Integration tests for the ERA 835 ingest endpoints."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt
from app.services.era.base import RemittanceClient, Transaction
from tests.integration.conftest import mut

pytestmark = pytest.mark.integration

# ── Auth patch targets (mirrored from test_claims_endpoints.py) ───────────────

_P_HEADER = "app.middleware.auth.jwt.get_unverified_header"
_P_KEY = "app.middleware.auth._get_public_key"
_P_DECODE = "app.middleware.auth.jwt.decode"


# ── Fake remittance client ────────────────────────────────────────────────────


class _FakeClient(RemittanceClient):
    def __init__(self, *args, **kwargs):
        pass

    async def poll_transactions(self, since):
        return [Transaction(transaction_id="txn-1")]

    async def fetch_era(self, transaction_id: str) -> dict:
        return {
            "transactions": [
                {
                    "payer": {"name": "DELTA"},
                    "detailInfo": [
                        {
                            "paymentInfo": [
                                {
                                    "claimPaymentInfo": {
                                        "patientControlNumber": "NOPE",
                                        "claimStatusCode": "1",
                                        "claimPaymentAmount": "0.00",
                                        "patientResponsibilityAmount": "0.00",
                                        "totalClaimChargeAmount": "0.00",
                                    }
                                }
                            ]
                        }
                    ],
                }
            ]
        }


# ── Seed helper (mirrors test_claims_endpoints.py _seed) ─────────────────────


async def _seed(session: AsyncSession, claims_submission_enabled: bool = True):
    from app.models.practice import Practice
    from app.models.user import PracticeUser, User

    practice = Practice(
        id=uuid.uuid4(),
        name="ERA Endpoint Test Practice",
        features={"claims_submission": claims_submission_enabled},
        billing_npi="1234567890",
        billing_taxonomy_code="1223G0001X",
        billing_tax_id_encrypted=encrypt("123456789"),
        clearinghouse_submitter_id="SUB1",
        clearinghouse_provider="stedi",
        clearinghouse_api_key_ssm_path="/dental/staging/clearinghouse/api_key",
    )
    session.add(practice)

    cognito_sub = f"era-sub-{uuid.uuid4().hex}"
    user = User(
        id=uuid.uuid4(),
        cognito_sub=cognito_sub,
        email=f"era-staff-{uuid.uuid4().hex[:6]}@test.local",
        full_name="ERA Staff",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    session.add(
        PracticeUser(
            practice_id=practice.id,
            user_id=user.id,
            role="admin",
            is_active=True,
        )
    )

    await session.commit()
    return practice, user, cognito_sub


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestPollERA:
    async def test_feature_gate_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """POST /era/poll against a practice without claims_submission enabled → 403."""
        practice, user, cognito_sub = await _seed(db_session, claims_submission_enabled=False)

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
            headers = {
                "Authorization": "Bearer test-token",
                "X-Practice-ID": str(practice.id),
            }
            resp = await client.post("/api/v1/era/poll", headers=mut(headers))

        assert resp.status_code == 403, resp.text

    async def test_poll_happy_path_unmatched(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Poll returns 200 with new==1 and unmatched==1 when PCN matches no claim."""
        practice, user, cognito_sub = await _seed(db_session)

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
            patch("app.routers.era.StediRemittanceClient", _FakeClient),
            patch("app.routers.era.get_ssm_parameter", return_value="fake-key"),
        ):
            headers = {
                "Authorization": "Bearer test-token",
                "X-Practice-ID": str(practice.id),
            }
            resp = await client.post("/api/v1/era/poll", headers=mut(headers))

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["new"] == 1
        assert body["unmatched"] == 1
        assert body["matched"] == 0


class TestUnmatchedListAndResolve:
    async def test_unmatched_list_and_resolve(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """After a poll, GET /era/unmatched returns ≥1 row; POST resolve returns resolved==true."""
        practice, user, cognito_sub = await _seed(db_session)

        decoded_token = {
            "sub": cognito_sub,
            "email": user.email,
            "cognito:groups": ["admin"],
        }
        headers = {
            "Authorization": "Bearer test-token",
            "X-Practice-ID": str(practice.id),
        }

        # Step 1: poll to create an unmatched record
        with (
            patch(_P_HEADER, return_value={"kid": "test-kid"}),
            patch(_P_KEY, new=AsyncMock(return_value="fake-public-key")),
            patch(_P_DECODE, return_value=decoded_token),
            patch("app.routers.era.StediRemittanceClient", _FakeClient),
            patch("app.routers.era.get_ssm_parameter", return_value="fake-key"),
        ):
            poll_resp = await client.post("/api/v1/era/poll", headers=mut(headers))
        assert poll_resp.status_code == 200, poll_resp.text

        # Step 2: list unmatched — should have at least 1 row
        with (
            patch(_P_HEADER, return_value={"kid": "test-kid"}),
            patch(_P_KEY, new=AsyncMock(return_value="fake-public-key")),
            patch(_P_DECODE, return_value=decoded_token),
        ):
            list_resp = await client.get(
                "/api/v1/era/unmatched",
                headers=headers,
                params={"resolved": "false"},
            )
        assert list_resp.status_code == 200, list_resp.text
        rows = list_resp.json()
        assert len(rows) >= 1
        unmatched_id = rows[0]["id"]

        # Step 3: resolve the first unmatched payment
        with (
            patch(_P_HEADER, return_value={"kid": "test-kid"}),
            patch(_P_KEY, new=AsyncMock(return_value="fake-public-key")),
            patch(_P_DECODE, return_value=decoded_token),
        ):
            resolve_resp = await client.post(
                f"/api/v1/era/unmatched/{unmatched_id}/resolve",
                headers=mut(headers),
            )
        assert resolve_resp.status_code == 200, resolve_resp.text
        resolved_body = resolve_resp.json()
        assert resolved_body["resolved"] is True
