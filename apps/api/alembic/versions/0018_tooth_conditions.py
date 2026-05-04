"""Tooth conditions per-patient tooth chart

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tooth_conditions",
        # ── Primary key ────────────────────────────────────────────────────
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # ── Practice / patient scope ───────────────────────────────────────
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        # ── Tooth identification ───────────────────────────────────────────
        sa.Column("tooth_number", sa.Text, nullable=False),
        sa.Column(
            "notation_system",
            sa.Text,
            sa.CheckConstraint(
                "notation_system IN ('universal', 'fdi')",
                name="ck_tooth_conditions_notation_system",
            ),
            nullable=False,
            server_default="universal",
        ),
        # ── Condition details ──────────────────────────────────────────────
        sa.Column(
            "condition_type",
            sa.Text,
            sa.CheckConstraint(
                "condition_type IN ('existing_restoration', 'missing', 'implant', 'crown', "
                "'bridge_pontic', 'bridge_abutment', 'root_canal', 'decay', 'fracture', "
                "'watch', 'other')",
                name="ck_tooth_conditions_condition_type",
            ),
            nullable=False,
        ),
        # Surfaces affected, e.g. 'MOD', 'B', 'L'; null for whole-tooth conditions
        sa.Column("surface", sa.Text, nullable=True),
        # e.g. 'composite', 'amalgam', 'PFM', 'zirconia'
        sa.Column("material", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "status",
            sa.Text,
            sa.CheckConstraint(
                "status IN ('existing', 'treatment_planned', 'completed_today')",
                name="ck_tooth_conditions_status",
            ),
            nullable=False,
            server_default="existing",
        ),
        # ── Visit metadata ─────────────────────────────────────────────────
        sa.Column("recorded_at", sa.Date, nullable=False),
        sa.Column("recorded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=True),
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
    )

    op.create_index(
        "ix_tooth_conditions_patient_recorded_at",
        "tooth_conditions",
        ["patient_id", sa.text("recorded_at DESC")],
    )
    op.create_index(
        "ix_tooth_conditions_patient_tooth_number",
        "tooth_conditions",
        ["patient_id", "tooth_number"],
    )
    op.create_index(
        "ix_tooth_conditions_appointment_id",
        "tooth_conditions",
        ["appointment_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tooth_conditions_appointment_id", table_name="tooth_conditions")
    op.drop_index("ix_tooth_conditions_patient_tooth_number", table_name="tooth_conditions")
    op.drop_index("ix_tooth_conditions_patient_recorded_at", table_name="tooth_conditions")
    op.drop_table("tooth_conditions")
