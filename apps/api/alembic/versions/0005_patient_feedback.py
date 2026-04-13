"""Add marital_status, medications, doctor_notes to patients; add patient_insurances table

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── patients: new columns ─────────────────────────────────────────────────
    op.add_column(
        "patients",
        sa.Column("marital_status", sa.String(20), nullable=True),
    )
    marital_values = (
        "('single', 'married', 'divorced', 'widowed', 'separated', 'domestic_partner', 'other')"
    )
    op.create_check_constraint(
        "ck_patients_marital_status",
        "patients",
        f"marital_status IN {marital_values}",
    )

    op.add_column(
        "patients",
        sa.Column(
            "medications",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )

    op.add_column(
        "patients",
        sa.Column("doctor_notes", sa.Text, nullable=True),
    )

    # ── patient_insurances: new table ─────────────────────────────────────────
    op.create_table(
        "patient_insurances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "priority",
            sa.String(10),
            nullable=False,
            server_default="primary",
        ),
        sa.Column("carrier", sa.String(255), nullable=False),
        sa.Column("member_id", sa.String(100), nullable=True),
        sa.Column("group_number", sa.String(100), nullable=True),
        sa.Column(
            "relationship_to_insured",
            sa.String(10),
            nullable=False,
            server_default="self",
        ),
        sa.Column("insured_first_name", sa.String(100), nullable=True),
        sa.Column("insured_last_name", sa.String(100), nullable=True),
        sa.Column("insured_date_of_birth", sa.Date, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
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
            "priority IN ('primary', 'secondary')",
            name="ck_patient_insurances_priority",
        ),
        sa.CheckConstraint(
            "relationship_to_insured IN ('self', 'spouse', 'child', 'other')",
            name="ck_patient_insurances_relationship",
        ),
    )
    op.create_index("ix_patient_insurances_patient_id", "patient_insurances", ["patient_id"])
    op.create_index(
        "ix_patient_insurances_practice_patient",
        "patient_insurances",
        ["practice_id", "patient_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_patient_insurances_practice_patient", table_name="patient_insurances")
    op.drop_index("ix_patient_insurances_patient_id", table_name="patient_insurances")
    op.drop_table("patient_insurances")

    op.drop_column("patients", "doctor_notes")
    op.drop_column("patients", "medications")
    op.drop_constraint("ck_patients_marital_status", "patients", type_="check")
    op.drop_column("patients", "marital_status")
