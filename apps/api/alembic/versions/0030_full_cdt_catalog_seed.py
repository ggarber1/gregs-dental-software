"""Seed the full ADA CDT catalog (codes + categories; fees stay null)

Revision ID: 0030
Revises: 0029
Create Date: 2026-06-16
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.data.cdt_catalog import CDT_CATALOG

revision: str = "0030"
down_revision: str | Sequence[str] | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    existing = {row[0] for row in conn.execute(sa.text("SELECT code FROM cdt_codes"))}
    rows = [
        {
            "id": uuid.uuid4(),
            "code": code,
            "description": desc,
            "category": cat,
            "default_fee_cents": None,
            "is_active": True,
        }
        for code, desc, cat in CDT_CATALOG
        if code not in existing
    ]
    if rows:
        meta = sa.MetaData()
        cdt = sa.Table("cdt_codes", meta, autoload_with=conn)
        op.bulk_insert(cdt, rows)


def downgrade() -> None:
    # Leave the catalog in place; the 20-code seed predates this migration and
    # appointment_procedures / fee rows may reference cdt_codes. No-op downgrade.
    pass
