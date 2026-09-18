"""Unit tests for /api/v1/patients/{id}/statements*. Auth, DB and services are mocked."""

from __future__ import annotations

import uuid
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.services.statements import service as statements

_PRACTICE_ID = uuid.uuid4()
_PATIENT_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_SUB = "cognito-sub-test"
_JWT_CLAIMS = {"sub": _SUB, "email": "staff@clinic.com", "cognito:groups": []}
_BASE = f"/api/v1/patients/{_PATIENT_ID}/statements"
_PDF = b"%PDF-1.7 fake"


@contextmanager
def _auth_patches(practice_id: uuid.UUID | None = _PRACTICE_ID, role: str = "front_desk"):
    membership_result = (_USER_ID, role) if practice_id is not None else None
    headers: dict[str, str] = {"Authorization": "Bearer fake.jwt.token"}
    if practice_id is not None:
        headers["X-Practice-ID"] = str(practice_id)
    with (
        patch("jose.jwt.get_unverified_header", return_value={"kid": "fake-kid"}),
        patch("app.middleware.auth._get_public_key", new=AsyncMock(return_value=object())),
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


def _mut(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Idempotency-Key": str(uuid.uuid4())}


def _feature_off() -> HTTPException:
    return HTTPException(status_code=403, detail={"error": {"code": "FEATURE_NOT_ENABLED"}})


def _fake_session_factory():
    session = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=cm)


def _statement(**overrides):
    base = dict(
        id=uuid.uuid4(),
        practice_id=_PRACTICE_ID,
        patient_id=_PATIENT_ID,
        delivery_method="email",
        balance_cents=7500,
        aging_snapshot={"b0_30": 0, "b31_60": 7500, "b61_90": 0, "b90_plus": 0},
        generated_at=datetime(2026, 9, 18, 12, 0, tzinfo=UTC),
        delivered_at=datetime(2026, 9, 18, 12, 0, tzinfo=UTC),
        generated_by=_SUB,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@contextmanager
def _router_patches(**service_overrides):
    """Patch the feature gate, the session factory, and any named service functions
    (looked up as attributes of the `statements` module imported by the router)."""
    with ExitStack() as stack:
        stack.enter_context(
            patch("app.routers.statements.require_feature", new=AsyncMock(return_value=None))
        )
        stack.enter_context(
            patch(
                "app.routers.statements.get_session_factory",
                return_value=_fake_session_factory(),
            )
        )
        for name, value in service_overrides.items():
            stack.enter_context(patch(f"app.routers.statements.statements.{name}", new=value))
        yield service_overrides


async def _client():
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_create_email_statement_returns_201_json():
    row = _statement()
    create = AsyncMock(return_value=row)
    with _auth_patches() as headers, _router_patches(create_statement=create):
        async with await _client() as client:
            resp = await client.post(_BASE, headers=_mut(headers), json={"deliveryMethod": "email"})

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] == str(row.id)
    assert body["deliveryMethod"] == "email"
    assert body["balanceCents"] == 7500
    assert body["buckets"] == {"b0_30": 0, "b31_60": 7500, "b61_90": 0, "b90_plus": 0}
    assert body["deliveredAt"].startswith("2026-09-18T12:00:00")
    assert body["generatedBy"] == _SUB
    kwargs = create.call_args.kwargs
    assert kwargs["delivery_method"] == "email"
    assert kwargs["generated_by"] == _SUB


@pytest.mark.asyncio
async def test_create_download_statement_has_null_delivered_at():
    row = _statement(delivery_method="download", delivered_at=None)
    with _auth_patches() as headers, _router_patches(create_statement=AsyncMock(return_value=row)):
        async with await _client() as client:
            resp = await client.post(
                _BASE, headers=_mut(headers), json={"deliveryMethod": "download"}
            )
    assert resp.status_code == 201, resp.text
    assert resp.json()["deliveredAt"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (
            statements.NoOutstandingBalanceError("No outstanding balance."),
            400,
            "NO_OUTSTANDING_BALANCE",
        ),
        (
            statements.NoPatientEmailError("Patient has no email address on file."),
            400,
            "PATIENT_HAS_NO_EMAIL",
        ),
        (LookupError("nope"), 404, "PATIENT_NOT_FOUND"),
        (RuntimeError("SES send_raw_email failed: boom"), 502, "EMAIL_DELIVERY_FAILED"),
    ],
)
async def test_create_statement_error_mapping(exc, status, code):
    with _auth_patches() as headers, _router_patches(create_statement=AsyncMock(side_effect=exc)):
        async with await _client() as client:
            resp = await client.post(_BASE, headers=_mut(headers), json={"deliveryMethod": "email"})
    assert resp.status_code == status, resp.text
    assert resp.json()["error"]["code"] == code


@pytest.mark.asyncio
async def test_create_statement_rejects_bad_delivery_method():
    with _auth_patches() as headers, _router_patches(create_statement=AsyncMock()):
        async with await _client() as client:
            resp = await client.post(_BASE, headers=_mut(headers), json={"deliveryMethod": "fax"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_statement_requires_write_role():
    with _auth_patches(role="read_only") as headers, _router_patches(create_statement=AsyncMock()):
        async with await _client() as client:
            resp = await client.post(_BASE, headers=_mut(headers), json={"deliveryMethod": "email"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "INSUFFICIENT_ROLE"


@pytest.mark.asyncio
async def test_list_statements():
    rows = [_statement(), _statement(delivery_method="download", delivered_at=None)]
    with _auth_patches() as headers, _router_patches(list_statements=AsyncMock(return_value=rows)):
        async with await _client() as client:
            resp = await client.get(_BASE, headers=headers)
    assert resp.status_code == 200, resp.text
    assert [s["deliveryMethod"] for s in resp.json()] == ["email", "download"]


@pytest.mark.asyncio
async def test_list_statements_gated_on_billing_ledger():
    from app.main import app

    with (
        _auth_patches() as headers,
        patch(
            "app.routers.statements.require_feature", new=AsyncMock(side_effect=_feature_off())
        ) as gate,
        patch("app.routers.statements.get_session_factory", return_value=_fake_session_factory()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(_BASE, headers=headers)
    assert resp.status_code == 403
    assert gate.call_args.args[2] == "billing_ledger"


@pytest.mark.asyncio
async def test_preview_returns_inline_pdf_and_records_nothing():
    render = AsyncMock(return_value=_PDF)
    create = AsyncMock()
    with (
        _auth_patches() as headers,
        _router_patches(render_statement_pdf=render, create_statement=create),
    ):
        async with await _client() as client:
            resp = await client.get(f"{_BASE}/preview", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["content-disposition"].startswith("inline;")
    assert resp.content == _PDF
    assert render.call_args.kwargs["require_balance"] is True
    create.assert_not_called()


@pytest.mark.asyncio
async def test_preview_without_balance_is_400():
    with (
        _auth_patches() as headers,
        _router_patches(
            render_statement_pdf=AsyncMock(side_effect=statements.NoOutstandingBalanceError("x"))
        ),
    ):
        async with await _client() as client:
            resp = await client.get(f"{_BASE}/preview", headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "NO_OUTSTANDING_BALANCE"


@pytest.mark.asyncio
async def test_statement_pdf_download_uses_recorded_date():
    row = _statement(delivery_method="download", delivered_at=None)
    render = AsyncMock(return_value=_PDF)
    with (
        _auth_patches() as headers,
        _router_patches(get_statement=AsyncMock(return_value=row), render_statement_pdf=render),
    ):
        async with await _client() as client:
            resp = await client.get(f"{_BASE}/{row.id}/pdf", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["content-disposition"] == 'attachment; filename="statement-2026-09-18.pdf"'
    assert resp.content == _PDF
    assert render.call_args.kwargs["statement_date"] == row.generated_at.date()
    assert render.call_args.kwargs["require_balance"] is False


@pytest.mark.asyncio
async def test_statement_pdf_unknown_id_is_404():
    with _auth_patches() as headers, _router_patches(get_statement=AsyncMock(return_value=None)):
        async with await _client() as client:
            resp = await client.get(f"{_BASE}/{uuid.uuid4()}/pdf", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "STATEMENT_NOT_FOUND"
