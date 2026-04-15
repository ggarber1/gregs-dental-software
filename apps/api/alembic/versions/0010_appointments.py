"""Appointment types and appointments tables

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. appointment_types ─────────────────────────────────────────────────
    op.create_table(
        "appointment_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "practice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("practices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("duration_minutes", sa.Integer, nullable=False),
        sa.Column("color", sa.String(7), nullable=False, server_default="#5B8DEF"),
        sa.Column(
            "default_cdt_codes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
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
        "ix_appointment_types_practice_id",
        "appointment_types",
        ["practice_id"],
    )
    op.create_index(
        "ix_appointment_types_practice_is_active",
        "appointment_types",
        ["practice_id", "is_active"],
    )

    # ── 2. appointments ──────────────────────────────────────────────────────
    op.create_table(
        "appointments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "practice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("practices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patients.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "provider_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("providers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "operatory_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("operatories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "appointment_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("appointment_types.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="scheduled",
        ),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("cancellation_reason", sa.Text, nullable=True),
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
            "status IN ('scheduled', 'confirmed', 'checked_in', 'in_chair', "
            "'completed', 'cancelled', 'no_show')",
            name="ck_appointments_status",
        ),
        sa.CheckConstraint(
            "end_time > start_time",
            name="ck_appointments_end_after_start",
        ),
    )
    op.create_index(
        "ix_appointments_practice_start_end",
        "appointments",
        ["practice_id", "start_time", "end_time"],
    )
    op.create_index(
        "ix_appointments_provider_start_end",
        "appointments",
        ["provider_id", "start_time", "end_time"],
    )
    op.create_index(
        "ix_appointments_operatory_start_end",
        "appointments",
        ["operatory_id", "start_time", "end_time"],
    )
    op.create_index(
        "ix_appointments_patient_id",
        "appointments",
        ["patient_id"],
    )
    op.create_index(
        "ix_appointments_practice_status",
        "appointments",
        ["practice_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("appointments")
    op.drop_table("appointment_types")
