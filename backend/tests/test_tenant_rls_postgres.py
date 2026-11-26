"""PostgreSQL 16 integration tests proving real Row-Level Security (RLS) tenant isolation."""

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.database import bind_tenant_rls, get_db
from app.core.security import create_access_token, get_password_hash, hash_token
from app.main import app as fastapi_app
from app.models.auth import User
from app.models.tenant import AuditLog, Membership, Organization, OrganizationInvitation, OrgRole

pytestmark = pytest.mark.integration


def _require_pg_integration_enabled() -> None:
    if os.getenv("FINSIGHT_RUN_PG_INTEGRATION") != "1":
        pytest.skip("Set FINSIGHT_RUN_PG_INTEGRATION=1 to run PostgreSQL RLS integration tests")


async def _make_pg_engine() -> AsyncEngine:
    get_settings.cache_clear()
    settings = get_settings()
    return create_async_engine(str(settings.DATABASE_URL), poolclass=NullPool)


async def _seed_rls_tenants(
    session: AsyncSession,
    *,
    user_a_id: uuid.UUID,
    user_b_id: uuid.UUID,
    org_a_id: uuid.UUID,
    org_b_id: uuid.UUID,
    suffix: str,
) -> None:
    now = datetime.now(UTC)
    pw_hash = get_password_hash("Strong!Pass2026#")
    session.add_all(
        [
            User(
                id=user_a_id,
                email=f"pg_a_{suffix}@example.com",
                password_hash=pw_hash,
                name="PG Tenant A",
                email_verified_at=now,
            ),
            User(
                id=user_b_id,
                email=f"pg_b_{suffix}@example.com",
                password_hash=pw_hash,
                name="PG Tenant B",
                email_verified_at=now,
            ),
            Organization(
                id=org_a_id,
                name=f"Org A {suffix}",
                slug=f"org-a-{suffix}",
                owner_id=user_a_id,
            ),
            Organization(
                id=org_b_id,
                name=f"Org B {suffix}",
                slug=f"org-b-{suffix}",
                owner_id=user_b_id,
            ),
            Membership(
                org_id=org_a_id,
                user_id=user_a_id,
                role=OrgRole.OWNER,
                invited_by_id=user_a_id,
                invited_at=now,
                accepted_at=now,
            ),
            Membership(
                org_id=org_b_id,
                user_id=user_b_id,
                role=OrgRole.OWNER,
                invited_by_id=user_b_id,
                invited_at=now,
                accepted_at=now,
            ),
            OrganizationInvitation(
                org_id=org_a_id,
                email=f"inv_a_{suffix}@example.com",
                role=OrgRole.ANALYST,
                token_hash=hash_token(f"tok_a_{suffix}"),
                invited_by_id=user_a_id,
                expires_at=now + timedelta(days=7),
            ),
            OrganizationInvitation(
                org_id=org_b_id,
                email=f"inv_b_{suffix}@example.com",
                role=OrgRole.VIEWER,
                token_hash=hash_token(f"tok_b_{suffix}"),
                invited_by_id=user_b_id,
                expires_at=now + timedelta(days=7),
            ),
            AuditLog(
                org_id=org_a_id,
                actor_id=user_a_id,
                action="org.created",
                target=f"org:{org_a_id}",
                event_metadata={"seed": "a"},
            ),
            AuditLog(
                org_id=org_b_id,
                actor_id=user_b_id,
                action="org.created",
                target=f"org:{org_b_id}",
                event_metadata={"seed": "b"},
            ),
        ]
    )
    await session.commit()


@pytest.mark.asyncio
async def test_postgres_rls_enforces_strict_tenant_isolation() -> None:
    """Verify PostgreSQL RLS blocks cross-tenant reads, writes, and unset-context queries."""
    _require_pg_integration_enabled()

    engine = await _make_pg_engine()
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    suffix = uuid.uuid4().hex[:8]
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    org_a_id = uuid.uuid4()
    org_b_id = uuid.uuid4()

    try:
        # 1. Confirm runtime role `finsight_app` exists without SUPERUSER or BYPASSRLS
        async with session_factory() as session:
            role_row = (
                await session.execute(
                    text(
                        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'finsight_app'"
                    )
                )
            ).one_or_none()
            assert role_row is not None
            assert role_row[0] is False
            assert role_row[1] is False

            await _seed_rls_tenants(
                session,
                user_a_id=user_a_id,
                user_b_id=user_b_id,
                org_a_id=org_a_id,
                org_b_id=org_b_id,
                suffix=suffix,
            )

        # 2. Unset tenant_id under `finsight_app` must see ZERO rows across all 4 tables
        async with session_factory() as session:
            await session.execute(text("SET LOCAL ROLE finsight_app"))
            await session.execute(text("SELECT set_config('app.current_tenant_id', '', true)"))
            for table in (
                "organizations",
                "memberships",
                "organization_invitations",
                "audit_logs",
            ):
                count = (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
                assert count == 0

        # 3. Bound to Tenant A: unfiltered SELECTs ONLY return Tenant A rows (never Tenant B!)
        async with session_factory() as session:
            await bind_tenant_rls(session, org_a_id, "finsight_app")

            org_ids = {
                row[0]
                for row in (await session.execute(text("SELECT id FROM organizations"))).all()
            }
            assert org_ids == {org_a_id}

            member_org_ids = {
                row[0]
                for row in (await session.execute(text("SELECT org_id FROM memberships"))).all()
            }
            assert member_org_ids == {org_a_id}

            inv_org_ids = {
                row[0]
                for row in (
                    await session.execute(text("SELECT org_id FROM organization_invitations"))
                ).all()
            }
            assert inv_org_ids == {org_a_id}

            audit_org_ids = {
                row[0]
                for row in (await session.execute(text("SELECT org_id FROM audit_logs"))).all()
            }
            assert audit_org_ids == {org_a_id}

            # Cross-tenant UPDATE and DELETE affect 0 rows
            upd = await session.execute(
                text("UPDATE organizations SET name = 'Tampered' WHERE id = :org_b"),
                {"org_b": org_b_id},
            )
            assert upd.rowcount == 0  # type: ignore[attr-defined]

            delete_audit = await session.execute(
                text("DELETE FROM audit_logs WHERE org_id = :org_b"),
                {"org_b": org_b_id},
            )
            assert delete_audit.rowcount == 0  # type: ignore[attr-defined]

            # Cross-tenant INSERT violates RLS WITH CHECK
            with pytest.raises(DBAPIError):
                await session.execute(
                    text(
                        "INSERT INTO audit_logs (id, org_id, actor_id, action, target, metadata, created_at, updated_at) "
                        "VALUES (:id, :org_b, :actor, 'spoof', 'org:b', '{}'::jsonb, NOW(), NOW())"
                    ),
                    {"id": uuid.uuid4(), "org_b": org_b_id, "actor": user_a_id},
                )
            await session.rollback()

        # 4. Subsequent transaction on same pooled connection defaults safely when bound to Tenant B
        async with session_factory() as session:
            await bind_tenant_rls(session, org_b_id, "finsight_app")
            org_ids_b = {
                row[0]
                for row in (await session.execute(text("SELECT id FROM organizations"))).all()
            }
            assert org_ids_b == {org_b_id}
    finally:
        # Clean up isolated synthetic test records cleanly
        async with session_factory() as cleanup:
            await cleanup.execute(
                text("DELETE FROM organizations WHERE id IN (:org_a, :org_b)"),
                {"org_a": org_a_id, "org_b": org_b_id},
            )
            await cleanup.execute(
                text("DELETE FROM users WHERE id IN (:ua, :ub)"),
                {"ua": user_a_id, "ub": user_b_id},
            )
            await cleanup.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_tenant_endpoints_against_real_postgres_rls() -> None:
    """Exercise FastAPI get_tenant_db + SET LOCAL ROLE finsight_app end-to-end against Postgres."""
    _require_pg_integration_enabled()

    engine = await _make_pg_engine()
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    suffix = uuid.uuid4().hex[:8]
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    org_a_id = uuid.uuid4()
    org_b_id = uuid.uuid4()

    async def override_pg_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    fastapi_app.dependency_overrides[get_db] = override_pg_db
    try:
        async with session_factory() as seed_session:
            await _seed_rls_tenants(
                seed_session,
                user_a_id=user_a_id,
                user_b_id=user_b_id,
                org_a_id=org_a_id,
                org_b_id=org_b_id,
                suffix=suffix,
            )

        token_a = create_access_token(str(user_a_id))
        token_b = create_access_token(str(user_b_id))

        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app),
            base_url="http://test",
        ) as client:
            ok_members = await client.get(
                f"/api/v1/orgs/{org_a_id}/members",
                headers={"Authorization": f"Bearer {token_a}"},
            )
            assert ok_members.status_code == 200
            assert len(ok_members.json()) == 1
            assert ok_members.json()[0]["user_id"] == str(user_a_id)

            renamed = await client.patch(
                f"/api/v1/orgs/{org_a_id}",
                json={"name": f"PG Updated Org A {suffix}"},
                headers={"Authorization": f"Bearer {token_a}"},
            )
            assert renamed.status_code == 200

            denied_cross = await client.get(
                f"/api/v1/orgs/{org_b_id}/audit-logs",
                headers={"Authorization": f"Bearer {token_a}"},
            )
            assert denied_cross.status_code == 403

            ok_b_logs = await client.get(
                f"/api/v1/orgs/{org_b_id}/audit-logs",
                headers={"Authorization": f"Bearer {token_b}"},
            )
            assert ok_b_logs.status_code == 200
            assert all(item["org_id"] == str(org_b_id) for item in ok_b_logs.json()["items"])
    finally:
        fastapi_app.dependency_overrides.clear()
        async with session_factory() as cleanup:
            await cleanup.execute(
                text("DELETE FROM organizations WHERE id IN (:org_a, :org_b)"),
                {"org_a": org_a_id, "org_b": org_b_id},
            )
            await cleanup.execute(
                text("DELETE FROM users WHERE id IN (:ua, :ub)"),
                {"ua": user_a_id, "ub": user_b_id},
            )
            await cleanup.commit()
        await engine.dispose()
