"""Create F1 authentication tables: users, refresh_tokens, auth_tokens.

Revision ID: 0002_f1_auth_tables
Revises: 0001_f0_baseline
Create Date: 2026-11-26 14:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_f1_auth_tables"
down_revision: str | None = "0001_f0_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create users, refresh_tokens, and auth_tokens tables."""
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("oauth_provider", sa.String(length=32), nullable=True),
        sa.Column("oauth_subject", sa.String(length=255), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_id", "users", ["id"], unique=False)
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index(
        "uq_users_oauth_provider_subject",
        "users",
        ["oauth_provider", "oauth_subject"],
        unique=True,
        postgresql_where=sa.text("oauth_provider IS NOT NULL AND oauth_subject IS NOT NULL"),
        sqlite_where=sa.text("oauth_provider IS NOT NULL AND oauth_subject IS NOT NULL"),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("family_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("replaced_by_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["replaced_by_id"], ["refresh_tokens.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_refresh_tokens_id", "refresh_tokens", ["id"], unique=False)
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False)
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"], unique=False)
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"], unique=False)

    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_auth_tokens_id", "auth_tokens", ["id"], unique=False)
    op.create_index("ix_auth_tokens_user_id", "auth_tokens", ["user_id"], unique=False)
    op.create_index("ix_auth_tokens_purpose", "auth_tokens", ["purpose"], unique=False)
    op.create_index("ix_auth_tokens_expires_at", "auth_tokens", ["expires_at"], unique=False)
    op.create_index(
        "ix_auth_tokens_user_purpose", "auth_tokens", ["user_id", "purpose"], unique=False
    )


def downgrade() -> None:
    """Drop F1 authentication tables."""
    op.drop_index("ix_auth_tokens_user_purpose", table_name="auth_tokens")
    op.drop_index("ix_auth_tokens_expires_at", table_name="auth_tokens")
    op.drop_index("ix_auth_tokens_purpose", table_name="auth_tokens")
    op.drop_index("ix_auth_tokens_user_id", table_name="auth_tokens")
    op.drop_index("ix_auth_tokens_id", table_name="auth_tokens")
    op.drop_table("auth_tokens")

    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index("uq_users_oauth_provider_subject", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")
