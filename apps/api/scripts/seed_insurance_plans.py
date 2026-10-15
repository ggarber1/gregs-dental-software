#!/usr/bin/env python3
"""
Seed common insurance carriers for a practice. Idempotent — safe to run repeatedly.

Required env vars:
  DATABASE_URL         — PostgreSQL connection string
  APP_ENCRYPTION_KEY   — Required by app startup

Usage:
  python -m scripts.seed_insurance_plans --practice-id <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.insurance_plan import InsurancePlan

# (carrier_name, payer_id). Plan ids are uuid5(practice_id, payer_id) so re-runs
# produce identical rows per practice; idempotency itself is the (practice_id,
# payer_id) lookup below.
_CARRIERS: list[tuple[str, str]] = [
    ("Delta Dental", "DLTADNTL"),
    ("MassHealth", "CKMA1"),
    ("Cigna", "CIGNA00"),
    ("Aetna", "AETNA00"),
    ("United Concordia", "UNITED0"),
    ("MetLife", "METLIF0"),
]


def carrier_plan_uuid(practice_id: uuid.UUID, payer_id: str) -> uuid.UUID:
    """Stable plan id, unique per practice + carrier."""
    return uuid.uuid5(practice_id, payer_id)


async def ensure_plans(session: AsyncSession, practice_id: uuid.UUID) -> None:
    """Add any missing common-carrier plans for the practice. Caller commits."""
    for carrier_name, payer_id in _CARRIERS:
        existing = await session.scalar(
            select(InsurancePlan).where(
                InsurancePlan.practice_id == practice_id,
                InsurancePlan.payer_id == payer_id,
                InsurancePlan.deleted_at.is_(None),
            )
        )
        if existing is not None:
            print(f"[seed] Plan already exists: {carrier_name} ({payer_id})")
            continue

        plan_id = carrier_plan_uuid(practice_id, payer_id)
        session.add(
            InsurancePlan(
                id=plan_id,
                practice_id=practice_id,
                carrier_name=carrier_name,
                payer_id=payer_id,
                is_in_network=True,
            )
        )
        print(f"[seed] Created plan: {carrier_name} ({payer_id}) id={plan_id}")


async def seed(practice_id: uuid.UUID) -> None:
    from app.core.config import get_settings

    engine = create_async_engine(get_settings().async_database_url, pool_pre_ping=True)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await ensure_plans(session, practice_id)
            await session.commit()
            print("[seed] Insurance plans seed complete.")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed common insurance carriers for a practice. Idempotent.",
    )
    parser.add_argument(
        "--practice-id",
        required=True,
        help="UUID of the practice to seed insurance plans for",
    )
    args = parser.parse_args()

    asyncio.run(seed(uuid.UUID(args.practice_id)))


if __name__ == "__main__":
    main()
