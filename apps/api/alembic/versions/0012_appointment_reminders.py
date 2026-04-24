"""Appointment reminders table

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "appointment_reminders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "practice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("practices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "appointment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("appointments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reminder_type", sa.String(10), nullable=False),
        sa.Column("hours_before", sa.Integer, nullable=False),
        sa.Column("send_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("sqs_message_id", sa.Text, nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text, nullable=True),
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
            "reminder_type IN ('sms', 'email')",
            name="ck_reminders_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'enqueued', 'sent', 'failed', 'cancelled')",
            name="ck_reminders_status",
        ),
    )
    op.create_index(
        "ix_appointment_reminders_appointment_id",
        "appointment_reminders",
        ["appointment_id"],
    )
    op.create_index(
        "ix_appointment_reminders_status_send_at",
        "appointment_reminders",
        ["status", "send_at"],
    )
    op.create_index(
        "ix_appointment_reminders_practice_appointment",
        "appointment_reminders",
        ["practice_id", "appointment_id"],
    )


def downgrade() -> None:
    op.drop_table("appointment_reminders")
