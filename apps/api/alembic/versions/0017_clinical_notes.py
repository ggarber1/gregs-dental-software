"""Clinical notes per appointment visit

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clinical_notes",
        # ── Primary key ────────────────────────────────────────────────────
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # ── Practice / patient / appointment scope ─────────────────────────
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Nullable: notes not tied to a scheduled appointment slot are allowed
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        # ── Visit metadata ─────────────────────────────────────────────────
        sa.Column("visit_date", sa.Date, nullable=False),
        # ── Clinical content fields ────────────────────────────────────────
        sa.Column("chief_complaint", sa.Text, nullable=True),
        sa.Column("anesthesia", sa.Text, nullable=True),
        sa.Column(
            "patient_tolerance",
            sa.Text,
            sa.CheckConstraint(
                "patient_tolerance IN ('excellent', 'good', 'fair', 'poor')",
                name="ck_clinical_notes_patient_tolerance",
            ),
            nullable=True,
        ),
        sa.Column("complications", sa.Text, nullable=True),
        sa.Column("treatment_rendered", sa.Text, nullable=False),
        sa.Column("next_visit_plan", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "template_type",
            sa.Text,
            sa.CheckConstraint(
                "template_type IN ('exam', 'prophy', 'extraction', 'crown_prep', "
                "'crown_seat', 'root_canal', 'filling', 'srp', 'other')",
                name="ck_clinical_notes_template_type",
            ),
            nullable=True,
        ),
        # ── Sign / lock fields ─────────────────────────────────────────────
        sa.Column(
            "is_signed",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signed_by_provider_id", postgresql.UUID(as_uuid=True), nullable=True),
        # ── PHI audit columns ──────────────────────────────────────────────
        sa.Column("last_accessed_by", sa.String(255), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        # ── Standard timestamps ────────────────────────────────────────────
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
        # One note per appointment; multiple notes without an appointment are allowed
        sa.UniqueConstraint("appointment_id", name="uq_clinical_notes_appointment_id"),
    )

    op.create_index(
        "ix_clinical_notes_patient_visit_date",
        "clinical_notes",
        ["patient_id", sa.text("visit_date DESC")],
    )
    op.create_index(
        "ix_clinical_notes_appointment_id",
        "clinical_notes",
        ["appointment_id"],
    )
    op.create_index(
        "ix_clinical_notes_practice_visit_date",
        "clinical_notes",
        ["practice_id", sa.text("visit_date DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_clinical_notes_practice_visit_date", table_name="clinical_notes")
    op.drop_index("ix_clinical_notes_appointment_id", table_name="clinical_notes")
    op.drop_index("ix_clinical_notes_patient_visit_date", table_name="clinical_notes")
    op.drop_table("clinical_notes")
