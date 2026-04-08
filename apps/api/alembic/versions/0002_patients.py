"""Add patients table

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "patients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Demographics
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("date_of_birth", sa.Date, nullable=False),
        sa.Column("sex", sa.String(10), nullable=True),
        # Contact
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        # Address
        sa.Column("address_line1", sa.Text, nullable=True),
        sa.Column("address_line2", sa.Text, nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(2), nullable=True),
        sa.Column("zip", sa.String(10), nullable=True),
        # PHI — AES-256-GCM encrypted last-4 SSN digits
        sa.Column("ssn_encrypted", postgresql.BYTEA(), nullable=True),
        # Clinical flags
        sa.Column(
            "allergies",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "medical_alerts",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "sms_opt_out",
            sa.Boolean,
            nullable=False,
            server_default="false",
        ),
        # PHIMixin timestamps
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
        # PHIMixin access tracking
        sa.Column("last_accessed_by", sa.String(255), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "sex IN ('male', 'female', 'other', 'unknown')",
            name="ck_patients_sex",
        ),
    )

    op.create_index("ix_patients_practice_id", "patients", ["practice_id"])
    op.create_index(
        "ix_patients_practice_name",
        "patients",
        ["practice_id", "last_name", "first_name"],
    )
    op.create_index(
        "ix_patients_practice_deleted",
        "patients",
        ["practice_id", "deleted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_patients_practice_deleted", table_name="patients")
    op.drop_index("ix_patients_practice_name", table_name="patients")
    op.drop_index("ix_patients_practice_id", table_name="patients")
    op.drop_table("patients")
