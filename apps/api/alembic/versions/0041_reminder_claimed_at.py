"""Reminders: replace sqs_message_id with claimed_at (scheduled job, no SQS)

Reminders are now claimed directly from the table by a scheduled job instead of
being handed to an SQS queue. `enqueued` now means "claimed for delivery";
claimed_at is the lease timestamp used to recover claims from a crashed run.

Revision ID: 0041
Revises: 0040
Create Date: 2026-10-22

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0041"
down_revision: str | Sequence[str] | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "appointment_reminders",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_column("appointment_reminders", "sqs_message_id")


def downgrade() -> None:
    op.add_column(
        "appointment_reminders",
        sa.Column("sqs_message_id", sa.Text(), nullable=True),
    )
    op.drop_column("appointment_reminders", "claimed_at")
