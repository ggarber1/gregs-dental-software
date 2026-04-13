"""Add emergency_contact, occupation, employer, referral_source to patients

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("emergency_contact_name", sa.String(200), nullable=True))
    op.add_column("patients", sa.Column("emergency_contact_phone", sa.String(20), nullable=True))
    op.add_column("patients", sa.Column("occupation", sa.String(200), nullable=True))
    op.add_column("patients", sa.Column("employer", sa.String(200), nullable=True))
    op.add_column("patients", sa.Column("referral_source", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("patients", "referral_source")
    op.drop_column("patients", "employer")
    op.drop_column("patients", "occupation")
    op.drop_column("patients", "emergency_contact_phone")
    op.drop_column("patients", "emergency_contact_name")
