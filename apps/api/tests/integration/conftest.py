"""
Integration test fixtures.

Requires a running Postgres at localhost:5432 (dental/dental) and Redis at localhost:6379.
The test database `dental_test` is created automatically if it does not exist.

Run with:
    pytest -m integration

All tables are truncated between tests — never run against production.
"""
from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Set env vars before any app module is imported.
os.environ["DATABASE_URL"] = "postgresql+asyncpg://dental:dental@localhost:5432/dental_test"
os.environ["APP_ENCRYPTION_KEY"] = "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleTEyMzQ="
os.environ["REDIS_URL"] = "redis://localhost:6379/1"  # DB 1 avoids dev collision

_TEST_DB_URL = "postgresql+asyncpg://dental:dental@localhost:5432/dental_test"

# Truncate in dependency-safe order; CASCADE handles any remaining FK deps.
_TRUNCATE_TABLES = (
    "intake_forms",
    "audit_logs",
    "patients",
    "practice_users",
    "users",
    "practices",
)


# ── Database bootstrap ─────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _ensure_test_db() -> None:
    """Create the dental_test database if it does not exist."""
    conn = await asyncpg.connect("postgresql://dental:dental@localhost:5432/dental")
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = 'dental_test'"
        )
        if not exists:
            await conn.execute("CREATE DATABASE dental_test")
    finally:
        await conn.close()


@pytest_asyncio.fixture(scope="session")
async def db_engine(_ensure_test_db: None) -> AsyncGenerator[AsyncEngine, None]:
    """Session-scoped async engine pointing at dental_test. Creates all tables once."""
    # Import models so they register with Base before create_all.
    import app.models  # noqa: F401 — triggers __init__ imports
    from app.models.base import Base

    engine = create_async_engine(_TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Function-scoped session. Truncates all tables after each test."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    # Tear-down: wipe all data so each test starts clean.
    async with db_engine.begin() as conn:
        tables = ", ".join(_TRUNCATE_TABLES)
        await conn.execute(text(f"TRUNCATE TABLE {tables} CASCADE"))


# ── App client ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client(db_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    """
    HTTPX async client wired to a fresh app instance backed by the test DB.

    Overrides the module-level globals in app.core.db so every call to
    get_session_factory() — regardless of import site — returns a factory
    bound to the test engine.
    """
    import app.core.db as _db_module
    from app.main import create_app

    test_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    _db_module._engine = db_engine
    _db_module._session_factory = test_factory
    try:
        app_instance = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app_instance), base_url="http://test"
        ) as c:
            yield c
    finally:
        _db_module._engine = None
        _db_module._session_factory = None


# ── Entity factories ───────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def practice(db_session: AsyncSession):
    """Insert a Practice row and return it."""
    from app.models.practice import Practice

    p = Practice(
        id=uuid.uuid4(),
        name="Sunrise Dental",
        timezone="America/New_York",
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest_asyncio.fixture
async def staff_user(db_session: AsyncSession, practice):
    """
    Insert a User + PracticeUser (admin) and return (user, cognito_sub).

    The cognito_sub is what the auth middleware looks up in the DB after
    JWT claims are decoded.
    """
    from app.models.user import PracticeUser, User

    cognito_sub = f"test-sub-{uuid.uuid4().hex}"
    user = User(
        id=uuid.uuid4(),
        cognito_sub=cognito_sub,
        email="staff@sunrise.test",
        full_name="Test Staff",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    pu = PracticeUser(
        practice_id=practice.id,
        user_id=user.id,
        role="admin",
        is_active=True,
    )
    db_session.add(pu)
    await db_session.commit()
    return user, cognito_sub


@pytest_asyncio.fixture
async def patient(db_session: AsyncSession, practice):
    """Insert a Patient row with a phone number and return it."""
    from app.models.patient import Patient

    p = Patient(
        id=uuid.uuid4(),
        practice_id=practice.id,
        first_name="Jane",
        last_name="Doe",
        date_of_birth=date(1990, 6, 15),
        phone="+15551234567",
        email="jane.doe@sunrise.test",
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


# ── Auth helpers ───────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def auth_headers(practice, staff_user):
    """
    HTTP headers for authenticated staff requests.

    Mocks out JWT signature validation while leaving _resolve_practice_membership
    to hit the real test DB — so the User / PracticeUser rows must exist first.
    """
    user, cognito_sub = staff_user

    with (
        patch(
            "app.middleware.auth.jwt.get_unverified_header",
            return_value={"kid": "test-kid"},
        ),
        patch(
            "app.middleware.auth._get_public_key",
            new=AsyncMock(return_value="fake-public-key"),
        ),
        patch(
            "app.middleware.auth.jwt.decode",
            return_value={
                "sub": cognito_sub,
                "email": user.email,
                "cognito:groups": ["admin"],
            },
        ),
    ):
        yield {
            "Authorization": "Bearer test-token",
            "X-Practice-ID": str(practice.id),
        }


# ── Shared form payload ────────────────────────────────────────────────────────


def mut(base_headers: dict, **extra: str) -> dict:
    """Return headers with a fresh Idempotency-Key for a single mutation request.

    Ensures each mutation hits the backend rather than getting a cached replay.
    """
    return {**base_headers, "Idempotency-Key": str(uuid.uuid4()), **extra}


def intake_submit_payload(**overrides: object) -> dict:
    """Return a valid SubmitIntakeForm JSON body. Override specific fields as needed."""
    now_iso = datetime.now(UTC).isoformat()
    base: dict = {
        "firstName": "Jane",
        "lastName": "Doe",
        "dateOfBirth": "1990-06-15",
        "sex": "female",
        "phone": "+15559876543",
        "email": "jane.updated@example.com",
        "addressLine1": "123 Main St",
        "city": "Boston",
        "state": "MA",
        "zip": "02101",
        "medicalConditions": ["diabetes", "hypertension"],
        "medications": ["metformin", "lisinopril"],
        "allergies": ["penicillin"],
        "lastDentalVisit": "2024-01-10",
        "chiefComplaint": "Tooth pain upper left",
        "insuranceCarrier": "Delta Dental",
        "insuranceMemberId": "DD123456",
        "insuranceGroupNumber": "GRP001",
        "insuranceHolderName": "Jane Doe",
        "insuranceHolderDob": "1990-06-15",
        "relationshipToInsured": "self",
        "hipaaConsentAccepted": True,
        "hipaaConsentTimestamp": now_iso,
        "hipaaConsentSignature": "Jane Doe",
        "smsOptIn": True,
    }
    base.update(overrides)
    return base
