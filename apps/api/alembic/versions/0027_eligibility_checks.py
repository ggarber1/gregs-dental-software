"""Reconcile eligibility_checks to spec: money->cents, add plan_name, relax raw_response

Revision ID: 0027
Revises: 0026
Create Date: 2026-06-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0027"
down_revision: str | Sequence[str] | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MONEY_COLS = (
    "deductible_individual",
    "deductible_individual_met",
    "deductible_family",
    "deductible_family_met",
    "oop_max_individual",
    "oop_max_individual_met",
    "annual_max_individual",
    "annual_max_individual_used",
    "annual_max_individual_remaining",
)


def upgrade() -> None:
    # Money: dollars (Numeric(10,2)) -> integer cents, per the absolute-cents convention.
    for col in _MONEY_COLS:
        op.alter_column(
            "eligibility_checks",
            col,
            type_=sa.Integer(),
            existing_type=sa.Numeric(10, 2),
            existing_nullable=True,
            postgresql_using=f"round({col} * 100)::integer",
        )
    # plan_name for the chart card.
    op.add_column("eligibility_checks", sa.Column("plan_name", sa.String(255), nullable=True))
    # raw_response is written only after a response arrives; pending rows have none.
    op.alter_column(
        "eligibility_checks",
        "raw_response",
        existing_type=postgresql.JSONB,
        nullable=True,
    )
    # Constrain clearinghouse values (0015 omitted this).
    op.create_check_constraint(
        "ck_eligibility_checks_clearinghouse",
        "eligibility_checks",
        "clearinghouse IN ('stedi', 'dentalxchange', 'manual')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_eligibility_checks_clearinghouse", "eligibility_checks", type_="check"
    )
    op.alter_column(
        "eligibility_checks",
        "raw_response",
        existing_type=postgresql.JSONB,
        nullable=False,
    )
    op.drop_column("eligibility_checks", "plan_name")
    for col in _MONEY_COLS:
        op.alter_column(
            "eligibility_checks",
            col,
            type_=sa.Numeric(10, 2),
            existing_type=sa.Integer(),
            existing_nullable=True,
            postgresql_using=f"({col} / 100.0)",
        )
