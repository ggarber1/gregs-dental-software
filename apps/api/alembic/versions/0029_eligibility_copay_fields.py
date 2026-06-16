"""Eligibility fields for Module 6 (plan_type, network, per-code coinsurance, waivers)

Revision ID: 0029
Revises: 0028
Create Date: 2026-06-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0029"
down_revision: str | Sequence[str] | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "eligibility_checks",
        sa.Column("plan_type", sa.String(20), nullable=False, server_default="ppo"),
    )
    op.add_column(
        "eligibility_checks",
        sa.Column(
            "network_status", sa.String(20), nullable=False, server_default="in_network"
        ),
    )
    op.add_column(
        "eligibility_checks",
        sa.Column("coinsurance_by_code", postgresql.JSONB, nullable=True),
    )
    op.add_column(
        "eligibility_checks",
        sa.Column(
            "deductible_waived_diagnostic", sa.Boolean, nullable=False, server_default="false"
        ),
    )
    op.add_column(
        "eligibility_checks",
        sa.Column(
            "deductible_waived_preventive", sa.Boolean, nullable=False, server_default="true"
        ),
    )
    op.add_column(
        "eligibility_checks",
        sa.Column(
            "deductible_waived_orthodontic", sa.Boolean, nullable=False, server_default="false"
        ),
    )
    op.add_column(
        "eligibility_checks", sa.Column("ortho_lifetime_max", sa.Integer, nullable=True)
    )
    op.add_column(
        "eligibility_checks", sa.Column("ortho_lifetime_max_used", sa.Integer, nullable=True)
    )
    op.create_check_constraint(
        "ck_eligibility_checks_plan_type",
        "eligibility_checks",
        "plan_type IN ('ppo', 'premier', 'medicaid', 'indemnity', 'dhmo')",
    )
    op.create_check_constraint(
        "ck_eligibility_checks_network_status",
        "eligibility_checks",
        "network_status IN ('in_network', 'out_of_network')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_eligibility_checks_network_status", "eligibility_checks", type_="check"
    )
    op.drop_constraint("ck_eligibility_checks_plan_type", "eligibility_checks", type_="check")
    for col in (
        "ortho_lifetime_max_used",
        "ortho_lifetime_max",
        "deductible_waived_orthodontic",
        "deductible_waived_preventive",
        "deductible_waived_diagnostic",
        "coinsurance_by_code",
        "network_status",
        "plan_type",
    ):
        op.drop_column("eligibility_checks", col)
