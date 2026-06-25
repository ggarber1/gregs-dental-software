"""Default billing_ledger feature ON (Module 8a)

Revision ID: 0035
Revises: 0034
Create Date: 2026-06-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0035"
down_revision: str | Sequence[str] | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Default the patient-ledger feature ON for new practices...
    op.alter_column(
        "practices",
        "features",
        server_default=sa.text("'{\"billing_ledger\": true}'::jsonb"),
        existing_type=postgresql.JSONB,
        existing_nullable=False,
    )
    # ...and backfill existing practices that don't already have the key set.
    op.execute(
        "UPDATE practices "
        "SET features = features || '{\"billing_ledger\": true}'::jsonb "
        "WHERE NOT (features ? 'billing_ledger')"
    )


def downgrade() -> None:
    op.alter_column(
        "practices",
        "features",
        server_default=sa.text("'{}'::jsonb"),
        existing_type=postgresql.JSONB,
        existing_nullable=False,
    )
    op.execute(
        "UPDATE practices "
        "SET features = features - 'billing_ledger' "
        "WHERE features ? 'billing_ledger'"
    )
