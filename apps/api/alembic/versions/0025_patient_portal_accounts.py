"""Add patient_portal_accounts table

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0025"
down_revision: str | Sequence[str] | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "patient_portal_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("cognito_sub", sa.Text, nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="invited",
        ),
        sa.Column("invite_token", sa.Text, nullable=True),
        sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('invited', 'active', 'revoked')",
            name="ck_patient_portal_accounts_status",
        ),
        sa.UniqueConstraint(
            "practice_id",
            "patient_id",
            name="uq_patient_portal_accounts_practice_patient",
        ),
    )

    op.create_index(
        "ix_patient_portal_accounts_invite_token",
        "patient_portal_accounts",
        ["invite_token"],
        unique=True,
    )
    op.create_index(
        "ix_patient_portal_accounts_cognito_sub",
        "patient_portal_accounts",
        ["cognito_sub"],
        unique=True,
    )
    op.create_index(
        "ix_patient_portal_accounts_practice_patient",
        "patient_portal_accounts",
        ["practice_id", "patient_id"],
    )
    op.create_index(
        "ix_patient_portal_accounts_practice_status",
        "patient_portal_accounts",
        ["practice_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_patient_portal_accounts_practice_status", table_name="patient_portal_accounts")
    op.drop_index("ix_patient_portal_accounts_practice_patient", table_name="patient_portal_accounts")
    op.drop_index("ix_patient_portal_accounts_cognito_sub", table_name="patient_portal_accounts")
    op.drop_index("ix_patient_portal_accounts_invite_token", table_name="patient_portal_accounts")
    op.drop_table("patient_portal_accounts")
