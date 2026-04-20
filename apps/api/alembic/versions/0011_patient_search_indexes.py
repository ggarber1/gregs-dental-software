"""Patient search: phone-digits expression index + DOB index

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-20

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_patients_phone_digits "
        "ON patients (regexp_replace(phone, '\\D', '', 'g')) "
        "WHERE deleted_at IS NULL"
    )
    op.create_index(
        "ix_patients_practice_dob",
        "patients",
        ["practice_id", "date_of_birth"],
    )


def downgrade() -> None:
    op.drop_index("ix_patients_practice_dob", table_name="patients")
    op.execute("DROP INDEX IF EXISTS ix_patients_phone_digits")
