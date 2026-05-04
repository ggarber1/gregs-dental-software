"""Treatment plans and treatment plan items

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "treatment_plans",
        # ── Primary key ────────────────────────────────────────────────────
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # ── Practice / patient scope ───────────────────────────────────────
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        # ── Plan details ───────────────────────────────────────────────────
        sa.Column("name", sa.Text, nullable=False, server_default="Treatment Plan"),
        sa.Column(
            "status",
            sa.Text,
            sa.CheckConstraint(
                "status IN ('proposed', 'accepted', 'in_progress', "
                "'completed', 'refused', 'superseded')",
                name="ck_treatment_plans_status",
            ),
            nullable=False,
            server_default="proposed",
        ),
        sa.Column("presented_at", sa.Date, nullable=True),
        sa.Column("accepted_at", sa.Date, nullable=True),
        sa.Column("completed_at", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
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
        "ix_treatment_plans_patient_status",
        "treatment_plans",
        ["patient_id", "status"],
    )
    op.create_index(
        "ix_treatment_plans_practice_status",
        "treatment_plans",
        ["practice_id", "status"],
    )
    op.create_index(
        "ix_treatment_plans_patient_created_at",
        "treatment_plans",
        ["patient_id", sa.text("created_at DESC")],
    )

    op.create_table(
        "treatment_plan_items",
        # ── Primary key ────────────────────────────────────────────────────
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # ── Practice / plan scope ──────────────────────────────────────────
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("treatment_plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        # ── Procedure details ──────────────────────────────────────────────
        sa.Column("tooth_number", sa.Text, nullable=True),
        sa.Column("procedure_code", sa.Text, nullable=False),
        sa.Column("procedure_name", sa.Text, nullable=False),
        sa.Column("surface", sa.Text, nullable=True),
        sa.Column("fee_cents", sa.Integer, nullable=False),
        sa.Column("insurance_est_cents", sa.Integer, nullable=True),
        sa.Column("patient_est_cents", sa.Integer, nullable=True),
        sa.Column(
            "status",
            sa.Text,
            sa.CheckConstraint(
                "status IN ('proposed', 'accepted', 'scheduled', 'completed', 'refused')",
                name="ck_treatment_plan_items_status",
            ),
            nullable=False,
            server_default="proposed",
        ),
        sa.Column("priority", sa.Integer, nullable=False, server_default="1"),
        # appointment_id is set when this item is scheduled
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=True),
        # completed_appointment_id is set when this item is completed
        sa.Column("completed_appointment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
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
        "ix_treatment_plan_items_plan_id",
        "treatment_plan_items",
        ["treatment_plan_id"],
    )
    op.create_index(
        "ix_treatment_plan_items_patient_status",
        "treatment_plan_items",
        ["patient_id", "status"],
    )
    op.create_index(
        "ix_treatment_plan_items_appointment_id",
        "treatment_plan_items",
        ["appointment_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_treatment_plan_items_appointment_id", table_name="treatment_plan_items")
    op.drop_index("ix_treatment_plan_items_patient_status", table_name="treatment_plan_items")
    op.drop_index("ix_treatment_plan_items_plan_id", table_name="treatment_plan_items")
    op.drop_table("treatment_plan_items")

    op.drop_index("ix_treatment_plans_patient_created_at", table_name="treatment_plans")
    op.drop_index("ix_treatment_plans_practice_status", table_name="treatment_plans")
    op.drop_index("ix_treatment_plans_patient_status", table_name="treatment_plans")
    op.drop_table("treatment_plans")
