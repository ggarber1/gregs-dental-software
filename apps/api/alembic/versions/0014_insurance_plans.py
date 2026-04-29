"""Insurance plans catalog and patient_insurance plan FK column

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "insurance_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("carrier_name", sa.String(255), nullable=False),
        sa.Column("payer_id", sa.String(50), nullable=False),
        sa.Column("group_number", sa.String(100), nullable=True),
        sa.Column("is_in_network", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
    )
    op.create_index(
        "ix_insurance_plans_practice_deleted",
        "insurance_plans",
        ["practice_id", "deleted_at"],
    )
    op.create_index(
        "ix_insurance_plans_practice_payer",
        "insurance_plans",
        ["practice_id", "payer_id"],
    )

    op.add_column(
        "patient_insurances",
        sa.Column("insurance_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_patient_insurances_plan_id",
        "patient_insurances",
        ["insurance_plan_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_patient_insurances_plan_id", table_name="patient_insurances")
    op.drop_column("patient_insurances", "insurance_plan_id")
    op.drop_index("ix_insurance_plans_practice_payer", table_name="insurance_plans")
    op.drop_index("ix_insurance_plans_practice_deleted", table_name="insurance_plans")
    op.drop_table("insurance_plans")
