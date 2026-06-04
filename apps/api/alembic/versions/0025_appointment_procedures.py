"""Appointment procedures and CDT code catalog

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-04
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0025"
down_revision: str | Sequence[str] | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (code, description, category, default_fee_cents) — ~20 common codes.
_SEED_CDT_CODES: list[tuple[str, str, str, int | None]] = [
    ("D0120", "Periodic oral evaluation - established patient", "diagnostic", None),
    ("D0140", "Limited oral evaluation - problem focused", "diagnostic", None),
    ("D0150", "Comprehensive oral evaluation - new/established patient", "diagnostic", None),
    ("D0210", "Intraoral - complete series of radiographic images", "diagnostic", None),
    ("D0220", "Intraoral - periapical first radiographic image", "diagnostic", None),
    ("D0274", "Bitewings - four radiographic images", "diagnostic", None),
    ("D1110", "Prophylaxis - adult", "preventive", None),
    ("D1120", "Prophylaxis - child", "preventive", None),
    ("D1206", "Topical application of fluoride varnish", "preventive", None),
    ("D1208", "Topical application of fluoride - excluding varnish", "preventive", None),
    ("D2140", "Amalgam - one surface, primary or permanent", "basic", None),
    ("D2150", "Amalgam - two surfaces, primary or permanent", "basic", None),
    ("D2330", "Resin-based composite - one surface, anterior", "basic", None),
    ("D2391", "Resin-based composite - one surface, posterior", "basic", None),
    ("D2392", "Resin-based composite - two surfaces, posterior", "basic", None),
    ("D2740", "Crown - porcelain/ceramic", "major", None),
    ("D2750", "Crown - porcelain fused to high noble metal", "major", None),
    ("D3220", "Therapeutic pulpotomy", "basic", None),
    ("D4341", "Periodontal scaling and root planing - four+ teeth per quadrant", "basic", None),
    ("D4342", "Periodontal scaling and root planing - one to three teeth per quadrant", "basic", None),
]


def upgrade() -> None:
    op.create_table(
        "cdt_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column(
            "category",
            sa.Text,
            sa.CheckConstraint(
                "category IN ('diagnostic', 'preventive', 'basic', 'major', 'ortho', 'other')",
                name="ck_cdt_codes_category",
            ),
            nullable=False,
        ),
        sa.Column("default_fee_cents", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_cdt_codes_code", "cdt_codes", ["code"])

    op.create_table(
        "appointment_procedures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cdt_code_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("procedure_code", sa.Text, nullable=True),
        sa.Column("procedure_name", sa.Text, nullable=False),
        sa.Column("tooth_number", sa.Text, nullable=True),
        sa.Column("surface", sa.Text, nullable=True),
        sa.Column("fee_cents", sa.Integer, nullable=False),
        sa.Column("insurance_est_cents", sa.Integer, nullable=True),
        sa.Column("patient_est_cents", sa.Integer, nullable=True),
        sa.Column("estimate_source", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("last_accessed_by", sa.String(255), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "cdt_code_id IS NOT NULL OR procedure_code IS NOT NULL",
            name="ck_appointment_procedures_code_present",
        ),
        sa.CheckConstraint(
            "estimate_source IS NULL OR "
            "estimate_source IN ('manual', 'eligibility', 'prior_eob')",
            name="ck_appointment_procedures_estimate_source",
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id"], ["appointments.id"],
            name="fk_appointment_procedures_appointment",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cdt_code_id"], ["cdt_codes.id"],
            name="fk_appointment_procedures_cdt_code",
        ),
    )
    op.create_index(
        "ix_appointment_procedures_appointment_id",
        "appointment_procedures", ["appointment_id"],
    )
    op.create_index(
        "ix_appointment_procedures_patient_created_at",
        "appointment_procedures", ["patient_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_appointment_procedures_cdt_code_id",
        "appointment_procedures", ["cdt_code_id"],
    )

    # Seed common CDT codes.
    cdt_table = sa.table(
        "cdt_codes",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.Text),
        sa.column("description", sa.Text),
        sa.column("category", sa.Text),
        sa.column("default_fee_cents", sa.Integer),
    )

    op.bulk_insert(
        cdt_table,
        [
            {
                "id": uuid.uuid4(),
                "code": code,
                "description": desc,
                "category": cat,
                "default_fee_cents": fee,
            }
            for (code, desc, cat, fee) in _SEED_CDT_CODES
        ],
    )


def downgrade() -> None:
    op.drop_table("appointment_procedures")
    op.drop_table("cdt_codes")
