"""Create F2 tenant/RBAC tables, audit_logs, and PostgreSQL Row-Level Security policies.

Revision ID: 0003_f2_tenants_rbac_and_rls
Revises: 0002_f1_auth_tables
Create Date: 2026-11-26 15:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_f2_tenants_rbac_and_rls"
down_revision: str | None = "0002_f1_auth_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT_POLICY_TABLES = (
    ("organizations", "id"),
    ("memberships", "org_id"),
    ("organization_invitations", "org_id"),
    ("audit_logs", "org_id"),
)


def upgrade() -> None:
    """Create organizations, memberships, invitations, audit_logs, backfill F1 users, enable RLS."""
    op.create_table(
        "organizations",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=140), nullable=False),
        sa.Column("owner_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organizations_id", "organizations", ["id"], unique=False)
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)
    op.create_index("ix_organizations_owner_id", "organizations", ["owner_id"], unique=False)
    op.create_index("ix_organizations_plan_id", "organizations", ["plan_id"], unique=False)

    op.create_table(
        "memberships",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("invited_by_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('owner', 'analyst', 'viewer')", name="ck_memberships_role"),
        sa.ForeignKeyConstraint(["invited_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "user_id", name="uq_memberships_org_user"),
    )
    op.create_index("ix_memberships_id", "memberships", ["id"], unique=False)
    op.create_index("ix_memberships_org_id", "memberships", ["org_id"], unique=False)
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"], unique=False)

    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('owner', 'analyst', 'viewer')",
            name="ck_org_invitations_role",
        ),
        sa.ForeignKeyConstraint(["invited_by_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_organization_invitations_id", "organization_invitations", ["id"], unique=False
    )
    op.create_index(
        "ix_organization_invitations_org_id", "organization_invitations", ["org_id"], unique=False
    )
    op.create_index(
        "ix_organization_invitations_email", "organization_invitations", ["email"], unique=False
    )
    op.create_index(
        "ix_organization_invitations_expires_at",
        "organization_invitations",
        ["expires_at"],
        unique=False,
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=255), nullable=False),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_id", "audit_logs", ["id"], unique=False)
    op.create_index("ix_audit_logs_org_id", "audit_logs", ["org_id"], unique=False)
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"], unique=False)
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"], unique=False)
    op.create_index(
        "ix_audit_logs_org_created_at",
        "audit_logs",
        ["org_id", "created_at"],
        unique=False,
    )

    # Backfill personal workspace for any existing F1 users lacking an active organization
    op.execute(
        sa.text("""
            WITH new_orgs AS (
                INSERT INTO organizations (id, name, slug, owner_id, plan_id, created_at, updated_at)
                SELECT
                    gen_random_uuid(),
                    LEFT(u.name || '''s Workspace', 120),
                    'ws-' || REPLACE(u.id::text, '-', ''),
                    u.id,
                    NULL,
                    NOW(),
                    NOW()
                FROM users u
                WHERE NOT EXISTS (
                    SELECT 1 FROM memberships m WHERE m.user_id = u.id
                )
                RETURNING id, owner_id, created_at, updated_at
            )
            INSERT INTO memberships (
                id, org_id, user_id, role, invited_by_id, invited_at, accepted_at, created_at, updated_at
            )
            SELECT
                gen_random_uuid(),
                no.id,
                no.owner_id,
                'owner',
                no.owner_id,
                no.created_at,
                no.created_at,
                no.created_at,
                no.updated_at
            FROM new_orgs no;
        """)
    )

    # Non-superuser runtime role (`NOBYPASSRLS`) and strict tenant RLS policies
    op.execute(
        sa.text("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finsight_app') THEN
                    CREATE ROLE finsight_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
                ELSE
                    ALTER ROLE finsight_app NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
                END IF;
            END
            $$;
        """)
    )
    op.execute(sa.text("GRANT USAGE ON SCHEMA public TO finsight_app;"))
    op.execute(sa.text("GRANT SELECT ON TABLE users TO finsight_app;"))
    op.execute(
        sa.text(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
            "organizations, memberships, organization_invitations, audit_logs TO finsight_app;"
        )
    )

    for table_name, tenant_col in _TENANT_POLICY_TABLES:
        op.execute(sa.text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;"))
        op.execute(sa.text(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;"))
        op.execute(
            sa.text(f"""
                CREATE POLICY tenant_isolation_{table_name}
                ON {table_name}
                FOR ALL
                USING (
                    {tenant_col} = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
                )
                WITH CHECK (
                    {tenant_col} = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
                );
            """)
        )


def downgrade() -> None:
    """Remove RLS policies and drop F2 tenant/RBAC tables."""
    for table_name, _ in reversed(_TENANT_POLICY_TABLES):
        op.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation_{table_name} ON {table_name};"))
        op.execute(sa.text(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY;"))

    op.execute(
        sa.text(
            "REVOKE ALL PRIVILEGES ON TABLE "
            "organizations, memberships, organization_invitations, audit_logs FROM finsight_app;"
        )
    )
    op.execute(sa.text("REVOKE SELECT ON TABLE users FROM finsight_app;"))

    op.drop_index("ix_audit_logs_org_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_org_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_id", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_organization_invitations_expires_at", table_name="organization_invitations")
    op.drop_index("ix_organization_invitations_email", table_name="organization_invitations")
    op.drop_index("ix_organization_invitations_org_id", table_name="organization_invitations")
    op.drop_index("ix_organization_invitations_id", table_name="organization_invitations")
    op.drop_table("organization_invitations")

    op.drop_index("ix_memberships_user_id", table_name="memberships")
    op.drop_index("ix_memberships_org_id", table_name="memberships")
    op.drop_index("ix_memberships_id", table_name="memberships")
    op.drop_table("memberships")

    op.drop_index("ix_organizations_plan_id", table_name="organizations")
    op.drop_index("ix_organizations_owner_id", table_name="organizations")
    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_index("ix_organizations_id", table_name="organizations")
    op.drop_table("organizations")
