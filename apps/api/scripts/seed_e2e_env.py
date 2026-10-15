#!/usr/bin/env python3
"""
Seed script for e2e test environments.

Creates the Practice + User + PracticeUser rows that the test Cognito user needs
to authenticate with a valid practice scope, plus one provider and one operatory
so the scheduling specs have something to book against. Idempotent — safe to run
on every deploy.

Required env vars:
  DATABASE_URL         — PostgreSQL connection string
  APP_ENCRYPTION_KEY   — Required by app startup

Usage:
  python -m scripts.seed_e2e_env \\
    --cognito-sub <sub>          \\
    --practice-id <uuid>         \\
    --email e2e@dental-e2e.internal \\
    --full-name "E2E Test User"  \\
    --practice-name "E2E Test Practice"

--practice-id must match the test user's `custom:practice_id` Cognito attribute.
Both values can be obtained via:
  aws cognito-idp admin-get-user --user-pool-id <pool_id> --username <email> \\
    --query 'UserAttributes[?Name==`sub` || Name==`custom:practice_id`]'
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.operatory import Operatory
from app.models.practice import Practice
from app.models.provider import Provider
from app.models.user import PracticeUser, User

# Fixed UUIDs so re-runs produce the same rows (idempotent by primary key).
E2E_PRACTICE_UUID = uuid.UUID("00000000-0000-0000-0000-e2e000000001")
E2E_USER_UUID = uuid.UUID("00000000-0000-0000-0000-e2e000000002")
E2E_PROVIDER_UUID = uuid.UUID("00000000-0000-0000-0000-e2e000000003")
E2E_OPERATORY_UUID = uuid.UUID("00000000-0000-0000-0000-e2e000000004")

# Luhn-valid placeholder NPI (the CMS documentation example) — never billed.
E2E_PROVIDER_NPI = "1234567893"


async def _ensure_practice(session: AsyncSession, practice_id: uuid.UUID, name: str) -> Practice:
    practice = await session.get(Practice, practice_id)
    if practice is not None:
        print(f"[seed] Practice already exists: {practice_id}")
        return practice
    practice = Practice(id=practice_id, name=name)
    session.add(practice)
    await session.flush()
    print(f"[seed] Created practice {practice_id} — {name!r}")
    return practice


async def _ensure_user(session: AsyncSession, cognito_sub: str, email: str, full_name: str) -> User:
    user = await session.scalar(select(User).where(User.cognito_sub == cognito_sub))
    if user is not None:
        print(f"[seed] User already exists: {user.id} (cognito_sub={user.cognito_sub!r})")
        return user
    user = User(id=E2E_USER_UUID, cognito_sub=cognito_sub, email=email, full_name=full_name)
    session.add(user)
    await session.flush()
    print(f"[seed] Created user {user.id} — cognito_sub={cognito_sub!r}")
    return user


async def _ensure_membership(session: AsyncSession, practice: Practice, user: User) -> None:
    membership = await session.scalar(
        select(PracticeUser).where(
            PracticeUser.practice_id == practice.id,
            PracticeUser.user_id == user.id,
        )
    )
    if membership is not None:
        print(f"[seed] Practice membership already exists (role={membership.role!r})")
        return
    session.add(PracticeUser(practice_id=practice.id, user_id=user.id, role="admin"))
    print(f"[seed] Created practice_user: practice={practice.id} user={user.id} role=admin")


async def _ensure_provider(session: AsyncSession, practice: Practice) -> None:
    if await session.get(Provider, E2E_PROVIDER_UUID) is not None:
        print(f"[seed] Provider already exists: {E2E_PROVIDER_UUID}")
        return
    session.add(
        Provider(
            id=E2E_PROVIDER_UUID,
            practice_id=practice.id,
            full_name="Dr. E2E Dentist",
            npi=E2E_PROVIDER_NPI,
            provider_type="dentist",
        )
    )
    print(f"[seed] Created provider {E2E_PROVIDER_UUID}")


async def _ensure_operatory(session: AsyncSession, practice: Practice) -> None:
    if await session.get(Operatory, E2E_OPERATORY_UUID) is not None:
        print(f"[seed] Operatory already exists: {E2E_OPERATORY_UUID}")
        return
    session.add(Operatory(id=E2E_OPERATORY_UUID, practice_id=practice.id, name="Operatory 1"))
    print(f"[seed] Created operatory {E2E_OPERATORY_UUID}")


async def seed_fixtures(
    session: AsyncSession,
    *,
    practice_id: uuid.UUID,
    cognito_sub: str,
    email: str,
    full_name: str,
    practice_name: str,
) -> None:
    """Create the e2e practice, user, membership, provider and operatory if missing."""
    practice = await _ensure_practice(session, practice_id, practice_name)
    user = await _ensure_user(session, cognito_sub, email, full_name)
    await _ensure_membership(session, practice, user)
    await _ensure_provider(session, practice)
    await _ensure_operatory(session, practice)
    await session.commit()


async def seed(
    *,
    practice_id: uuid.UUID,
    cognito_sub: str,
    email: str,
    full_name: str,
    practice_name: str,
) -> None:
    from app.core.config import get_settings
    from scripts.seed_insurance_plans import seed as seed_plans

    engine = create_async_engine(get_settings().async_database_url, pool_pre_ping=True)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await seed_fixtures(
                session,
                practice_id=practice_id,
                cognito_sub=cognito_sub,
                email=email,
                full_name=full_name,
                practice_name=practice_name,
            )
    finally:
        await engine.dispose()
    print("[seed] Done.")

    await seed_plans(practice_id)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed e2e test fixtures (practice, user, provider, operatory). Idempotent.",
    )
    parser.add_argument(
        "--cognito-sub",
        required=True,
        help="Cognito sub of the e2e test user (from AdminGetUser)",
    )
    parser.add_argument(
        "--practice-id",
        type=uuid.UUID,
        default=E2E_PRACTICE_UUID,
        help="Must match the test user's custom:practice_id Cognito attribute",
    )
    parser.add_argument("--email", default="e2e@dental-e2e.internal")
    parser.add_argument("--full-name", default="E2E Test User")
    parser.add_argument("--practice-name", default="E2E Test Practice")
    args = parser.parse_args()

    asyncio.run(
        seed(
            practice_id=args.practice_id,
            cognito_sub=args.cognito_sub,
            email=args.email,
            full_name=args.full_name,
            practice_name=args.practice_name,
        )
    )


if __name__ == "__main__":
    main()
