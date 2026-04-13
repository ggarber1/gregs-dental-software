#!/usr/bin/env python3
"""
One-time seed script for e2e test environments.

Creates the Practice + User + PracticeUser rows that the test Cognito user needs
to authenticate with a valid practice scope. Idempotent — safe to run repeatedly.

Required env vars:
  DATABASE_URL         — PostgreSQL connection string
  APP_ENCRYPTION_KEY   — Required by app startup

Usage:
  python scripts/seed_e2e_env.py \\
    --cognito-sub <sub>          \\
    --email e2e@dental-e2e.internal \\
    --full-name "E2E Test User"  \\
    --practice-name "E2E Test Practice"

The cognito-sub can be obtained via:
  aws cognito-idp admin-get-user --user-pool-id <pool_id> --username <email> \\
    --query 'UserAttributes[?Name==`sub`].Value' --output text
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Fixed UUIDs so re-runs produce the same rows (idempotent by primary key).
E2E_PRACTICE_UUID = uuid.UUID("00000000-0000-0000-0000-e2e000000001")
E2E_USER_UUID = uuid.UUID("00000000-0000-0000-0000-e2e000000002")


async def seed(
    *,
    cognito_sub: str,
    email: str,
    full_name: str,
    practice_name: str,
) -> None:
    # Import here so the script fails fast with a clear error if DATABASE_URL is missing.
    from app.core.config import get_settings
    from app.models.practice import Practice
    from app.models.user import PracticeUser, User

    settings = get_settings()
    engine = create_async_engine(settings.async_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            # ── Practice ──────────────────────────────────────────────────────
            practice = await session.scalar(
                select(Practice).where(Practice.id == E2E_PRACTICE_UUID)
            )
            if practice is None:
                practice = Practice(id=E2E_PRACTICE_UUID, name=practice_name)
                session.add(practice)
                await session.flush()
                print(f"[seed] Created practice {E2E_PRACTICE_UUID} — {practice_name!r}")
            else:
                print(f"[seed] Practice already exists: {E2E_PRACTICE_UUID}")

            # ── User ──────────────────────────────────────────────────────────
            user = await session.scalar(select(User).where(User.cognito_sub == cognito_sub))
            if user is None:
                user = User(
                    id=E2E_USER_UUID,
                    cognito_sub=cognito_sub,
                    email=email,
                    full_name=full_name,
                )
                session.add(user)
                await session.flush()
                print(f"[seed] Created user {user.id} — cognito_sub={cognito_sub!r}")
            else:
                print(f"[seed] User already exists: {user.id} (cognito_sub={user.cognito_sub!r})")

            # ── PracticeUser ──────────────────────────────────────────────────
            practice_user = await session.scalar(
                select(PracticeUser).where(
                    PracticeUser.practice_id == practice.id,
                    PracticeUser.user_id == user.id,
                )
            )
            if practice_user is None:
                practice_user = PracticeUser(
                    practice_id=practice.id,
                    user_id=user.id,
                    role="admin",
                )
                session.add(practice_user)
                print(
                    f"[seed] Created practice_user: "
                    f"practice={practice.id} user={user.id} role=admin"
                )
            else:
                print(f"[seed] Practice membership already exists (role={practice_user.role!r})")

            await session.commit()
            print("[seed] Done.")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed e2e test fixtures (practice + user + membership). Idempotent.",
    )
    parser.add_argument(
        "--cognito-sub",
        required=True,
        help="Cognito sub of the e2e test user (from AdminGetUser)",
    )
    parser.add_argument("--email", default="e2e@dental-e2e.internal")
    parser.add_argument("--full-name", default="E2E Test User")
    parser.add_argument("--practice-name", default="E2E Test Practice")
    args = parser.parse_args()

    asyncio.run(
        seed(
            cognito_sub=args.cognito_sub,
            email=args.email,
            full_name=args.full_name,
            practice_name=args.practice_name,
        )
    )


if __name__ == "__main__":
    main()
