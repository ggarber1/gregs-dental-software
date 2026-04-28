#!/usr/bin/env python3
"""
Seed common insurance carriers for a practice. Idempotent — safe to run repeatedly.

Required env vars:
  DATABASE_URL         — PostgreSQL connection string
  APP_ENCRYPTION_KEY   — Required by app startup

Usage:
  python scripts/seed_insurance_plans.py --practice-id <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Fixed UUIDs per carrier so re-runs produce identical rows (idempotent).
# These are global across practices; each practice gets its own copy keyed by
# (CARRIER_BASE_UUID XOR practice_id) is NOT used here — instead we look up by
# (practice_id, payer_id) so the UUID is stable per practice+carrier pair.
_CARRIERS: list[tuple[str, str, str]] = [
    # (carrier_name, payer_id, seed_uuid_suffix)
    ("Delta Dental", "DLTADNTL", "0000000000c1"),
    ("MassHealth", "CKMA1", "0000000000c2"),
    ("Cigna", "CIGNA00", "0000000000c3"),
    ("Aetna", "AETNA00", "0000000000c4"),
    ("United Concordia", "UNITED0", "0000000000c5"),
    ("MetLife", "METLIF0", "0000000000c6"),
]


def _carrier_uuid(practice_id: uuid.UUID, suffix: str) -> uuid.UUID:
    """Stable UUID derived from practice_id and a per-carrier suffix."""
    c = str(practice_id).replace("-", "") + suffix
    return uuid.UUID(f"{c[:8]}-{c[8:12]}-{c[12:16]}-{c[16:20]}-{c[20:32]}")


async def seed(practice_id: uuid.UUID) -> None:
    from app.core.config import get_settings
    from app.models.insurance_plan import InsurancePlan

    settings = get_settings()
    engine = create_async_engine(settings.async_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            for carrier_name, payer_id, suffix in _CARRIERS:
                plan_id = _carrier_uuid(practice_id, suffix)

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

                plan = InsurancePlan(
                    id=plan_id,
                    practice_id=practice_id,
                    carrier_name=carrier_name,
                    payer_id=payer_id,
                    is_in_network=True,
                )
                session.add(plan)
                print(f"[seed] Created plan: {carrier_name} ({payer_id}) id={plan_id}")

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
