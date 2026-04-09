"""Add intake_forms table

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "intake_forms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        # 64-char hex-encoded 32 cryptographically random bytes
        sa.Column("token", sa.Text, nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        # AES-256-GCM encrypted JSON blob of form responses; null until submitted
        sa.Column("responses_encrypted", postgresql.BYTEA(), nullable=True),
        sa.Column("submission_ip", sa.Text, nullable=True),
        sa.Column("submission_user_agent", sa.Text, nullable=True),
        # ID of the practice_user who sent the link
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        # Timestamps
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
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'expired')",
            name="ck_intake_forms_status",
        ),
    )

    op.create_index("ix_intake_forms_token", "intake_forms", ["token"], unique=True)
    op.create_index(
        "ix_intake_forms_practice_patient",
        "intake_forms",
        ["practice_id", "patient_id"],
    )
    op.create_index(
        "ix_intake_forms_practice_status",
        "intake_forms",
        ["practice_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_intake_forms_practice_status", table_name="intake_forms")
    op.drop_index("ix_intake_forms_practice_patient", table_name="intake_forms")
    op.drop_index("ix_intake_forms_token", table_name="intake_forms")
    op.drop_table("intake_forms")
