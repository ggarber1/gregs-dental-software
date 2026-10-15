"""Add appointment_attachments table

Revision ID: 0038
Revises: 0037
Create Date: 2026-07-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0038"
down_revision: str | Sequence[str] | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "appointment_attachments",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("practice_id", sa.UUID(), nullable=False),
        sa.Column("appointment_id", sa.UUID(), nullable=False),
        sa.Column("s3_key", sa.Text(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("attachment_type", sa.String(30), nullable=False),
        sa.Column("uploaded_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_by", sa.String(255), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'application/pdf',"
            " 'image/tiff', 'text/plain')",
            name="ck_appointment_attachments_content_type",
        ),
        sa.CheckConstraint(
            "attachment_type IN ('xray', 'photo', 'perio_narrative', 'lab_rx', 'other')",
            name="ck_appointment_attachments_attachment_type",
        ),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_appt_attachments_appointment",
        "appointment_attachments",
        ["appointment_id"],
    )
    op.create_index(
        "ix_appt_attachments_practice",
        "appointment_attachments",
        ["practice_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_appt_attachments_practice", "appointment_attachments")
    op.drop_index("ix_appt_attachments_appointment", "appointment_attachments")
    op.drop_table("appointment_attachments")
