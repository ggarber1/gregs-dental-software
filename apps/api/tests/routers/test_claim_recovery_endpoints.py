"""Endpoint tests for claim recovery: resubmit + write-off + patient_id filter."""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.services.claims.service import ClaimSubmissionPrereqError

# ── Constants ─────────────────────────────────────────────────────────────────

_PRACTICE_ID = uuid.uuid4()
_CLAIM_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_JWT_CLAIMS = {"sub": "staff-sub", "email": "staff@clinic.com", "cognito:groups": []}


# ── Helpers ───────────────────────────────────────────────────────────────────


@contextmanager
def _auth_patches(practice_id: uuid.UUID | None = _PRACTICE_ID, role: str = "front_desk"):
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


def _fake_session_factory_empty_list():
    """Session whose scalars() returns an empty list."""
    session = AsyncMock()
    scalars_result = MagicMock()
    scalars_result.all = MagicMock(return_value=[])
    session.scalars = AsyncMock(return_value=scalars_result)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock(return_value=cm)
    return factory


def _fake_claim_row(submission_attempt: int = 2) -> MagicMock:
    """MagicMock that satisfies _to_schema() field accesses."""
    now = datetime.now(UTC)
    m = MagicMock()
    m.id = _CLAIM_ID
    m.practice_id = _PRACTICE_ID
    m.appointment_id = uuid.uuid4()
    m.patient_id = uuid.uuid4()
    m.insurance_id = uuid.uuid4()
    m.provider_id = uuid.uuid4()
    m.idempotency_key = "key"
    m.submission_attempt = submission_attempt
    m.patient_control_number = f"PCN-{submission_attempt}"
    m.payer_id = "DELTA"
    m.status = "submitted"
    m.total_charge_cents = 100000
    m.clearinghouse_claim_id = None
    m.clearinghouse_status = None
    m.submission_errors = None
    m.insurance_paid_cents = None
    m.patient_responsibility_cents = None
    m.payer_claim_control_number = None
    m.adjustments = None
    m.denial_codes = None
    m.paid_at = None
    m.remittance_id = None
    m.submitted_at = now
    m.created_at = now
    m.updated_at = now
    return m


# ── Tests: resubmit ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resubmit_happy_path():
    from app.main import create_app

    app = create_app()
    fake_claim = _fake_claim_row(submission_attempt=2)

    with _auth_patches() as headers, patch(
        "app.routers.claims.require_feature", new=AsyncMock(return_value=None)
    ), patch(
        "app.routers.claims.feature_enabled", return_value=False
    ), patch(
        "app.routers.claims.get_ssm_parameter", return_value="fake-api-key"
    ), patch(
        "app.routers.claims.StediClaimsClient", return_value=MagicMock()
    ), patch(
        "app.routers.claims.resubmit_claim", new=AsyncMock(return_value=fake_claim)
    ), patch(
        "app.routers.claims.get_session_factory", return_value=_fake_session_factory()
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/claims/{_CLAIM_ID}/resubmit",
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert resp.status_code == 200
    assert resp.json()["submissionAttempt"] == 2


@pytest.mark.asyncio
async def test_resubmit_feature_gate():
    from app.main import create_app

    app = create_app()

    with _auth_patches() as headers, patch(
        "app.routers.claims.require_feature",
        new=AsyncMock(side_effect=_feature_off()),
    ), patch(
        "app.routers.claims.get_session_factory", return_value=_fake_session_factory()
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/claims/{_CLAIM_ID}/resubmit",
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_resubmit_not_found():
    from app.main import create_app

    app = create_app()

    with _auth_patches() as headers, patch(
        "app.routers.claims.require_feature", new=AsyncMock(return_value=None)
    ), patch(
        "app.routers.claims.feature_enabled", return_value=False
    ), patch(
        "app.routers.claims.get_ssm_parameter", return_value="fake-api-key"
    ), patch(
        "app.routers.claims.StediClaimsClient", return_value=MagicMock()
    ), patch(
        "app.routers.claims.resubmit_claim",
        new=AsyncMock(
            side_effect=ClaimSubmissionPrereqError("CLAIM_NOT_FOUND", "Claim not found")
        ),
    ), patch(
        "app.routers.claims.get_session_factory", return_value=_fake_session_factory()
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/claims/{_CLAIM_ID}/resubmit",
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "CLAIM_NOT_FOUND"


@pytest.mark.asyncio
async def test_resubmit_not_resubmittable():
    from app.main import create_app

    app = create_app()

    with _auth_patches() as headers, patch(
        "app.routers.claims.require_feature", new=AsyncMock(return_value=None)
    ), patch(
        "app.routers.claims.feature_enabled", return_value=False
    ), patch(
        "app.routers.claims.get_ssm_parameter", return_value="fake-api-key"
    ), patch(
        "app.routers.claims.StediClaimsClient", return_value=MagicMock()
    ), patch(
        "app.routers.claims.resubmit_claim",
        new=AsyncMock(
            side_effect=ClaimSubmissionPrereqError(
                "CLAIM_NOT_RESUBMITTABLE", "Claim status 'paid' is not resubmittable"
            )
        ),
    ), patch(
        "app.routers.claims.get_session_factory", return_value=_fake_session_factory()
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/claims/{_CLAIM_ID}/resubmit",
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "CLAIM_NOT_RESUBMITTABLE"


# ── Tests: write-off ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_write_off_happy_path():
    from app.main import create_app

    app = create_app()
    fake_claim = _fake_claim_row()
    fake_entry = MagicMock()
    fake_entry.id = uuid.uuid4()

    # session.scalar returns the claim row for _get_claim_by_id
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=fake_claim)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock(return_value=cm)

    with _auth_patches() as headers, patch(
        "app.routers.claims.require_feature", new=AsyncMock(return_value=None)
    ), patch(
        "app.routers.claims.write_off_claim", new=AsyncMock(return_value=fake_entry)
    ), patch(
        "app.routers.claims.get_session_factory", return_value=factory
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/claims/{_CLAIM_ID}/write-off",
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                json={},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert "claim" in body
    assert "ledgerEntry" in body
    assert body["ledgerEntry"] == str(fake_entry.id)


@pytest.mark.asyncio
async def test_write_off_with_memo():
    from app.main import create_app

    app = create_app()
    fake_claim = _fake_claim_row()

    session = AsyncMock()
    session.scalar = AsyncMock(return_value=fake_claim)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock(return_value=cm)

    captured: dict = {}

    async def _fake_write_off(session, practice_id, claim_id, *, memo, user_sub):
        captured["memo"] = memo
        return None  # no balance to write off

    with _auth_patches() as headers, patch(
        "app.routers.claims.require_feature", new=AsyncMock(return_value=None)
    ), patch(
        "app.routers.claims.write_off_claim", new=_fake_write_off
    ), patch(
        "app.routers.claims.get_session_factory", return_value=factory
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/claims/{_CLAIM_ID}/write-off",
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                json={"memo": "patient dispute resolved"},
            )
    assert resp.status_code == 200
    assert captured["memo"] == "patient dispute resolved"
    assert resp.json()["ledgerEntry"] is None


@pytest.mark.asyncio
async def test_write_off_already_resolved():
    from app.main import create_app

    app = create_app()

    with _auth_patches() as headers, patch(
        "app.routers.claims.require_feature", new=AsyncMock(return_value=None)
    ), patch(
        "app.routers.claims.write_off_claim",
        new=AsyncMock(
            side_effect=ClaimSubmissionPrereqError("ALREADY_RESOLVED", "Claim is already resolved")
        ),
    ), patch(
        "app.routers.claims.get_session_factory", return_value=_fake_session_factory()
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/claims/{_CLAIM_ID}/write-off",
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                json={},
            )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "ALREADY_RESOLVED"


@pytest.mark.asyncio
async def test_write_off_feature_gate():
    from app.main import create_app

    app = create_app()

    with _auth_patches() as headers, patch(
        "app.routers.claims.require_feature",
        new=AsyncMock(side_effect=_feature_off()),
    ), patch(
        "app.routers.claims.get_session_factory", return_value=_fake_session_factory()
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/claims/{_CLAIM_ID}/write-off",
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                json={},
            )
    assert resp.status_code == 403


# ── Tests: GET /claims patient_id filter ─────────────────────────────────────


@pytest.mark.asyncio
async def test_list_claims_patient_id_filter():
    from app.main import create_app

    app = create_app()
    patient_id = uuid.uuid4()

    with _auth_patches() as headers, patch(
        "app.routers.claims.require_feature", new=AsyncMock(return_value=None)
    ), patch(
        "app.routers.claims.get_session_factory",
        return_value=_fake_session_factory_empty_list(),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/v1/claims?patient_id={patient_id}",
                headers=headers,
            )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_claims_no_filter():
    from app.main import create_app

    app = create_app()

    with _auth_patches() as headers, patch(
        "app.routers.claims.require_feature", new=AsyncMock(return_value=None)
    ), patch(
        "app.routers.claims.get_session_factory",
        return_value=_fake_session_factory_empty_list(),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/claims", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []
