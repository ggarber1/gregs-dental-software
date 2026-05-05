"""Perio charts and readings

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "perio_charts",
        # ── Primary key ────────────────────────────────────────────────────
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # ── Practice / patient scope ───────────────────────────────────────
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        # ── Chart details ──────────────────────────────────────────────────
        sa.Column("chart_date", sa.Date, nullable=False),
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
        "ix_perio_charts_patient_date",
        "perio_charts",
        ["patient_id", sa.text("chart_date DESC")],
    )
    op.create_index("ix_perio_charts_practice", "perio_charts", ["practice_id"])

    op.create_table(
        "perio_readings",
        # ── Primary key ────────────────────────────────────────────────────
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # ── Chart scope ────────────────────────────────────────────────────
        sa.Column("perio_chart_id", postgresql.UUID(as_uuid=True), nullable=False),
        # ── Tooth / site identification ────────────────────────────────────
        sa.Column("tooth_number", sa.Text, nullable=False),
        sa.Column(
            "site",
            sa.Text,
            sa.CheckConstraint(
                "site IN ('db', 'b', 'mb', 'dl', 'l', 'ml')",
                name="ck_perio_readings_site",
            ),
            nullable=False,
        ),
        # ── Clinical measurements ──────────────────────────────────────────
        sa.Column(
            "probing_depth_mm",
            sa.SmallInteger,
            sa.CheckConstraint(
                "probing_depth_mm BETWEEN 0 AND 20",
                name="ck_perio_readings_depth",
            ),
            nullable=False,
        ),
        sa.Column(
            "recession_mm",
            sa.SmallInteger,
            sa.CheckConstraint(
                "recession_mm BETWEEN 0 AND 15",
                name="ck_perio_readings_recession",
            ),
            nullable=False,
            server_default="0",
        ),
        sa.Column("bleeding", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("suppuration", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "furcation",
            sa.Text,
            sa.CheckConstraint(
                "furcation IS NULL OR furcation IN ('I', 'II', 'III')",
                name="ck_perio_readings_furcation",
            ),
            nullable=True,
        ),
        sa.Column(
            "mobility",
            sa.SmallInteger,
            sa.CheckConstraint(
                "mobility IS NULL OR mobility BETWEEN 0 AND 3",
                name="ck_perio_readings_mobility",
            ),
            nullable=True,
        ),
        # ── Timestamp ─────────────────────────────────────────────────────
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # ── Uniqueness: one reading per (chart, tooth, site) ───────────────
        sa.UniqueConstraint(
            "perio_chart_id",
            "tooth_number",
            "site",
            name="uq_perio_readings_chart_tooth_site",
        ),
    )

    op.create_index("ix_perio_readings_chart_id", "perio_readings", ["perio_chart_id"])


def downgrade() -> None:
    op.drop_index("ix_perio_readings_chart_id", table_name="perio_readings")
    op.drop_table("perio_readings")

    op.drop_index("ix_perio_charts_practice", table_name="perio_charts")
    op.drop_index("ix_perio_charts_patient_date", table_name="perio_charts")
    op.drop_table("perio_charts")
