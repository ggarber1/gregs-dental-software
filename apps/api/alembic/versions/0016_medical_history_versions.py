"""Medical history versioned snapshots per patient

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "medical_history_versions",
        # ── Primary key ────────────────────────────────────────────────────
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # ── Practice / patient scope ───────────────────────────────────────
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        # ── Versioning ─────────────────────────────────────────────────────
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("recorded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        # ── Structured PHI fields ──────────────────────────────────────────
        sa.Column(
            "allergies",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "medications",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "conditions",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # ── Dental-specific flags (computed on write) ──────────────────────
        sa.Column(
            "flag_blood_thinners",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "flag_bisphosphonates",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "flag_heart_condition",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "flag_diabetes",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "flag_pacemaker",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "flag_latex_allergy",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        # ── Free text overflow ─────────────────────────────────────────────
        sa.Column("additional_notes", sa.Text, nullable=True),
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
        # ── Unique: prevents duplicate version numbers under concurrent writes
        sa.UniqueConstraint(
            "patient_id",
            "version_number",
            name="uq_medical_history_versions_patient_version",
        ),
    )

    op.create_index(
        "ix_medical_history_versions_patient_id",
        "medical_history_versions",
        ["patient_id"],
    )
    op.create_index(
        "ix_medical_history_versions_practice_patient",
        "medical_history_versions",
        ["practice_id", "patient_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_medical_history_versions_practice_patient",
        table_name="medical_history_versions",
    )
    op.drop_index(
        "ix_medical_history_versions_patient_id",
        table_name="medical_history_versions",
    )
    op.drop_table("medical_history_versions")
