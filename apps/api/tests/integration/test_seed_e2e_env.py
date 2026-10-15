"""Integration tests for scripts/seed_e2e_env.py — the staging e2e fixture seed."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operatory import Operatory
from app.models.practice import Practice
from app.models.provider import Provider
from app.models.user import PracticeUser, User
from scripts.seed_e2e_env import E2E_OPERATORY_UUID, E2E_PROVIDER_UUID, seed_fixtures

pytestmark = pytest.mark.integration

_SUB = "e2e-cognito-sub"


async def _seed(session: AsyncSession, practice_id: uuid.UUID) -> None:
    await seed_fixtures(
        session,
        practice_id=practice_id,
        cognito_sub=_SUB,
        email="e2e@example.com",
        full_name="E2E Test User",
        practice_name="E2E Test Practice",
    )


async def _count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def test_creates_practice_user_provider_and_operatory(db_session: AsyncSession) -> None:
    practice_id = uuid.uuid4()

    await _seed(db_session, practice_id)

    assert (await db_session.get(Practice, practice_id)) is not None
    user = await db_session.scalar(select(User).where(User.cognito_sub == _SUB))
    assert user is not None
    membership = await db_session.scalar(
        select(PracticeUser).where(PracticeUser.user_id == user.id)
    )
    assert membership is not None
    assert membership.practice_id == practice_id
    assert membership.role == "admin"
    provider = await db_session.get(Provider, E2E_PROVIDER_UUID)
    assert provider is not None and provider.practice_id == practice_id
    operatory = await db_session.get(Operatory, E2E_OPERATORY_UUID)
    assert operatory is not None and operatory.practice_id == practice_id


async def test_rerun_creates_no_duplicates(db_session: AsyncSession) -> None:
    practice_id = uuid.uuid4()

    await _seed(db_session, practice_id)
    await _seed(db_session, practice_id)

    for model in (Practice, User, PracticeUser, Provider, Operatory):
        assert await _count(db_session, model) == 1, model.__name__
