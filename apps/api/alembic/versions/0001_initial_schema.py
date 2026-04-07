"""Initial schema: audit_logs, practices, users, practice_users, providers, operatories

Revision ID: 0001
Revises:
Create Date: 2026-04-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. audit_logs ─────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_logs_practice_id", "audit_logs", ["practice_id"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])
    op.create_index(
        "ix_audit_logs_practice_timestamp",
        "audit_logs",
        ["practice_id", "timestamp"],
    )

    # ── 2. practices ──────────────────────────────────────────────────────────
    op.create_table(
        "practices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column(
            "timezone",
            sa.String(64),
            nullable=False,
            server_default="America/New_York",
        ),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("address_line1", sa.Text, nullable=True),
        sa.Column("address_line2", sa.Text, nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(2), nullable=True),
        sa.Column("zip", sa.String(10), nullable=True),
        sa.Column(
            "features",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("clearinghouse_provider", sa.String(20), nullable=True),
        sa.Column("clearinghouse_submitter_id", sa.Text, nullable=True),
        sa.Column("clearinghouse_api_key_ssm_path", sa.Text, nullable=True),
        sa.Column("billing_npi", sa.String(10), nullable=True),
        sa.Column("billing_tax_id_encrypted", postgresql.BYTEA(), nullable=True),
        sa.Column("billing_taxonomy_code", sa.String(20), nullable=True),
        sa.Column("masshealth_provider_id", sa.Text, nullable=True),
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
            "clearinghouse_provider IN ('stedi', 'dentalxchange')",
            name="ck_practices_clearinghouse_provider",
        ),
    )

    # ── 3. users ──────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cognito_sub", sa.String(255), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
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
    )
    op.create_index("ix_users_cognito_sub", "users", ["cognito_sub"], unique=True)

    # ── 4. practice_users ─────────────────────────────────────────────────────
    op.create_table(
        "practice_users",
        sa.Column(
            "practice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("practices.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('admin', 'provider', 'front_desk', 'billing', 'read_only')",
            name="ck_practice_users_role",
        ),
    )
    # Index on user_id alone: "list all practices this user can access" (practice switcher).
    op.create_index("ix_practice_users_user_id", "practice_users", ["user_id"])

    # ── 5. providers ──────────────────────────────────────────────────────────
    op.create_table(
        "providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "practice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("practices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("npi", sa.String(10), nullable=False),
        sa.Column("provider_type", sa.String(20), nullable=False),
        sa.Column("license_number", sa.String(50), nullable=True),
        sa.Column("specialty", sa.Text, nullable=True),
        sa.Column("color", sa.String(7), nullable=False, server_default="#4F86C6"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
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
            "provider_type IN ('dentist', 'hygienist', 'specialist', 'other')",
            name="ck_providers_provider_type",
        ),
    )
    op.create_index("ix_providers_practice_id", "providers", ["practice_id"])
    op.create_index("ix_providers_npi", "providers", ["npi"])
    op.create_index(
        "ix_providers_practice_is_active",
        "providers",
        ["practice_id", "is_active"],
    )

    # ── 6. operatories ────────────────────────────────────────────────────────
    op.create_table(
        "operatories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "practice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("practices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("color", sa.String(7), nullable=False, server_default="#7BC67E"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
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
    )
    op.create_index("ix_operatories_practice_id", "operatories", ["practice_id"])
    op.create_index(
        "ix_operatories_practice_is_active",
        "operatories",
        ["practice_id", "is_active"],
    )

    # ── 7. audit_logs immutability trigger ────────────────────────────────────
    # Enforced at the DB layer independent of application code or DB user privileges.
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_logs_immutable()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs rows are immutable';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_audit_logs_no_update
            BEFORE UPDATE ON audit_logs
            FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable()
    """)
    op.execute("""
        CREATE TRIGGER trg_audit_logs_no_delete
            BEFORE DELETE ON audit_logs
            FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable()
    """)


def downgrade() -> None:
    # Drop triggers and function first (depend on audit_logs table).
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_no_update ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_no_delete ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_immutable()")

    op.drop_table("operatories")
    op.drop_table("providers")
    op.drop_table("practice_users")
    op.drop_table("users")
    op.drop_table("practices")
    op.drop_table("audit_logs")
