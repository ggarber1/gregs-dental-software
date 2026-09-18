"""Patient statements (Module 8b) — append-only delivery record

Revision ID: 0039
Revises: 0038
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0039"
down_revision: str | Sequence[str] | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "patient_statements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("delivery_method", sa.String(20), nullable=False),
        sa.Column("balance_cents", sa.Integer, nullable=False),
        sa.Column("aging_snapshot", postgresql.JSONB, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_by", sa.String(255), nullable=False),
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
        sa.Column("last_accessed_by", sa.String(255), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "delivery_method IN ('email', 'download')",
            name="ck_patient_statements_delivery_method",
        ),
    )
    op.create_index(
        "ix_patient_statements_patient_generated",
        "patient_statements",
        ["practice_id", "patient_id", "generated_at"],
    )
    op.create_index(
        "ix_patient_statements_practice_generated",
        "patient_statements",
        ["practice_id", "generated_at"],
    )


def downgrade() -> None:
    op.drop_table("patient_statements")
