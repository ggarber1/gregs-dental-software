"""Reminder delivery fields: twilio_message_sid, response tracking, email_opt_out

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # appointment_reminders: idempotency SID + inbound reply tracking
    op.add_column("appointment_reminders", sa.Column("twilio_message_sid", sa.Text, nullable=True))
    op.add_column("appointment_reminders", sa.Column("response_received", sa.Text, nullable=True))
    op.add_column(
        "appointment_reminders",
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
    )

    # patients: email opt-out parallel to existing sms_opt_out
    op.add_column(
        "patients",
        sa.Column(
            "email_opt_out",
            sa.Boolean,
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("patients", "email_opt_out")
    op.drop_column("appointment_reminders", "responded_at")
    op.drop_column("appointment_reminders", "response_received")
    op.drop_column("appointment_reminders", "twilio_message_sid")
