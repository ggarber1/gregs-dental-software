"""
Unit tests for GET /api/v1/reports/insurance-ar/* and POST action endpoints.

Auth and DB are fully mocked — no real Postgres, Cognito, or Redis needed.
JWT verification is patched out; practice membership is stubbed per-test.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.services.reports.insurance_ar import WorklistRow

# ── Constants ─────────────────────────────────────────────────────────────────

_PRACTICE_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_SUB = "cognito-sub-test"
_JWT_CLAIMS = {"sub": _SUB, "email": "staff@clinic.com", "cognito:groups": []}


# ── Helpers ───────────────────────────────────────────────────────────────────


@contextmanager
def _auth_patches(practice_id: uuid.UUID | None = _PRACTICE_ID, role: str = "front_desk"):
    """
    Patch Cognito JWT validation and practice membership resolution.

    Yields (auth_headers) — the headers to include in each request.
    If practice_id is None, X-Practice-ID is omitted (no practice scope).
    """
    membership_result = (_USER_ID, role) if practice_id is not None else None

    headers: dict[str, str] = {"Authorization": "Bearer fake.jwt.token"}
    if practice_id is not None:
        headers["X-Practice-ID"] = str(practice_id)

    with (
        patch("jose.jwt.get_unverified_header", return_value={"kid": "fake-kid"}),
        patch(
            "app.middleware.auth._get_public_key",
            new=AsyncMock(return_value=object()),
        ),
        patch("jose.jwt.decode", return_value=_JWT_CLAIMS),
        patch(
            "app.middleware.auth._resolve_practice_membership",
            new=AsyncMock(return_value=membership_result),
        ),
        patch(
            "app.middleware.idempotency.get_redis",
            return_value=AsyncMock(get=AsyncMock(return_value=None), setex=AsyncMock()),
        ),
    ):
        yield headers


def _feature_off() -> HTTPException:
    return HTTPException(status_code=403, detail={"error": {"code": "FEATURE_NOT_ENABLED"}})


def _fake_session_factory():
    session = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock(return_value=cm)
    return factory


def _sample_row() -> WorklistRow:
    return WorklistRow(
        claim_id=uuid.uuid4(),
        claim_number="PCN-1",
        patient_name="Jane Doe",
        payer_id="DELTA",
        carrier_name="Delta Dental",
        category="underpaid",
        billed_cents=120000,
        estimated_insurance_cents=84000,
        insurance_paid_cents=20000,
        shortfall_cents=64000,
        has_estimate=True,
        days_out=45,
        bucket="31-60",
        status="partially_paid",
        reason=None,
    )


# ── Task 8: worklist + summary ────────────────────────────────────────────────



@pytest.mark.asyncio
async def test_worklist_requires_feature_off_returns_403():
    from app.main import create_app

    app = create_app()
    with _auth_patches() as headers, patch(
        "app.routers.reports.require_feature",
        new=AsyncMock(side_effect=_feature_off()),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/reports/insurance-ar/claims", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_worklist_returns_rows():
    from app.main import create_app

    app = create_app()
    rows = [_sample_row()]
    with _auth_patches() as headers, patch(
        "app.routers.reports.require_feature", new=AsyncMock(return_value=None)
    ), patch(
        "app.routers.reports.insurance_ar.get_worklist",
        new=AsyncMock(return_value=rows),
    ), patch(
        "app.routers.reports.get_session_factory",
        return_value=_fake_session_factory(),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/reports/insurance-ar/claims", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["category"] == "underpaid"
    assert body[0]["billedCents"] == 120000


# ── Task 9: accept + appeal ───────────────────────────────────────────────────


def _accepted_claim():
    from datetime import UTC, datetime

    return MagicMock(
        id=uuid.uuid4(),
        status="partially_paid",
        insurance_reviewed_at=datetime(2026, 6, 29, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_accept_endpoint_returns_action_result():
    from app.main import create_app

    app = create_app()
    claim = _accepted_claim()
    cid = claim.id
    with _auth_patches() as headers, patch(
        "app.routers.reports.require_feature", new=AsyncMock(return_value=None)
    ), patch(
        "app.routers.reports.insurance_ar.accept_underpayment",
        new=AsyncMock(return_value=claim),
    ), patch(
        "app.routers.reports.get_session_factory", return_value=_fake_session_factory()
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/reports/insurance-ar/claims/{cid}/accept",
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                json={},
            )
    assert resp.status_code == 200
    assert resp.json()["status"] == "partially_paid"


@pytest.mark.asyncio
async def test_accept_endpoint_404_when_not_underpaid():
    from app.main import create_app

    app = create_app()
    with _auth_patches() as headers, patch(
        "app.routers.reports.require_feature", new=AsyncMock(return_value=None)
    ), patch(
        "app.routers.reports.insurance_ar.accept_underpayment",
        new=AsyncMock(side_effect=ValueError("not underpaid")),
    ), patch(
        "app.routers.reports.get_session_factory", return_value=_fake_session_factory()
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/reports/insurance-ar/claims/{uuid.uuid4()}/accept",
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                json={},
            )
    assert resp.status_code == 409
