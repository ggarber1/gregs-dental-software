"""Integration tests for scripts/seed_insurance_plans.py."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.insurance_plan import InsurancePlan
from app.models.practice import Practice
from scripts.seed_insurance_plans import _CARRIERS, ensure_plans

pytestmark = pytest.mark.integration


async def _practice(session: AsyncSession) -> uuid.UUID:
    practice = Practice(id=uuid.uuid4(), name="Plan Seed Practice")
    session.add(practice)
    await session.flush()
    return practice.id


async def _plan_count(session: AsyncSession, practice_id: uuid.UUID) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(InsurancePlan)
        .where(InsurancePlan.practice_id == practice_id)
    )
    return count or 0


async def test_seeds_every_carrier_once(db_session: AsyncSession) -> None:
    practice_id = await _practice(db_session)

    await ensure_plans(db_session, practice_id)
    await db_session.commit()

    assert await _plan_count(db_session, practice_id) == len(_CARRIERS)


async def test_rerun_and_second_practice_do_not_collide(db_session: AsyncSession) -> None:
    first, second = await _practice(db_session), await _practice(db_session)

    await ensure_plans(db_session, first)
    await db_session.commit()
    await ensure_plans(db_session, first)
    await ensure_plans(db_session, second)
    await db_session.commit()

    assert await _plan_count(db_session, first) == len(_CARRIERS)
    assert await _plan_count(db_session, second) == len(_CARRIERS)
