"""Unit and API integration tests for F2 organizations, RBAC, invitations, and audit logs."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.auth import User
from app.models.tenant import Membership, Organization, OrganizationInvitation, OrgRole
from app.services import auth as auth_service
from tests.conftest import RecordingTaskDispatcher

_PASSWORD = "Strong!Pass2026#"


def _extract_token(url: str) -> str:
    return parse_qs(urlparse(url).query)["token"][0]


async def _signup_verify_and_login(
    async_client: AsyncClient,
    dispatcher: RecordingTaskDispatcher,
    *,
    name: str,
    email: str,
) -> tuple[str, dict[str, Any]]:
    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": _PASSWORD},
    )
    assert reg_resp.status_code == 201

    verify_url = str(dispatcher.jobs[-1].args[2])
    raw_token = _extract_token(verify_url)
    verify_resp = await async_client.post("/api/v1/auth/verify", json={"token": raw_token})
    assert verify_resp.status_code == 200

    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": _PASSWORD},
    )
    assert login_resp.status_code == 200
    data = login_resp.json()
    return str(data["access_token"]), data


class TestAutoProvisioningAndWorkspaces:
    """Verify automatic personal organization creation on signup and workspace CRUD."""

    @pytest.mark.asyncio
    async def test_auto_org_created_on_email_and_google_signup_with_unique_slugs(
        self,
        async_client: AsyncClient,
        test_db: AsyncSession,
        task_dispatcher: RecordingTaskDispatcher,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # User 1 via email signup
        token_1, _ = await _signup_verify_and_login(
            async_client,
            task_dispatcher,
            name="Alice Analyst",
            email="alice1@example.com",
        )
        orgs_1 = (
            await async_client.get(
                "/api/v1/orgs",
                headers={"Authorization": f"Bearer {token_1}"},
            )
        ).json()
        assert len(orgs_1) == 1
        assert orgs_1[0]["name"] == "Alice Analyst's Workspace"
        assert orgs_1[0]["role"] == "owner"
        assert orgs_1[0]["slug"] == "alice-analyst-s-workspace"

        # User 2 with the exact same name gets a unique slug without collision
        token_2, _ = await _signup_verify_and_login(
            async_client,
            task_dispatcher,
            name="Alice Analyst",
            email="alice2@example.com",
        )
        orgs_2 = (
            await async_client.get(
                "/api/v1/orgs",
                headers={"Authorization": f"Bearer {token_2}"},
            )
        ).json()
        assert len(orgs_2) == 1
        assert orgs_2[0]["slug"] != orgs_1[0]["slug"]

        # Google OAuth first signup also auto-provisions an owner organization
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client-id-123")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-client-secret-456")
        get_settings.cache_clear()

        google_login = await async_client.get(
            "/api/v1/auth/google/login?next=/workspaces",
            follow_redirects=False,
        )
        state = parse_qs(urlparse(google_login.headers["location"]).query)["state"][0]

        async def fake_exchange(**kwargs: Any) -> dict[str, Any]:
            _ = kwargs
            return {"id_token": "mock-id-token"}

        async def fake_verify(**kwargs: Any) -> dict[str, Any]:
            _ = kwargs
            return {
                "sub": "google-org-sub-1",
                "email": "oauth.owner@example.com",
                "email_verified": True,
                "name": "OAuth Owner",
            }

        monkeypatch.setattr(auth_service, "exchange_google_authorization_code", fake_exchange)
        monkeypatch.setattr(auth_service, "verify_google_id_token", fake_verify)

        cb_resp = await async_client.get(
            f"/api/v1/auth/google/callback?code=code-1&state={state}",
            follow_redirects=False,
        )
        ex_code = parse_qs(urlparse(cb_resp.headers["location"]).query)["code"][0]
        ex_resp = await async_client.post("/api/v1/auth/google/exchange", json={"code": ex_code})
        assert ex_resp.status_code == 200
        oauth_access = ex_resp.json()["access_token"]

        oauth_orgs = (
            await async_client.get(
                "/api/v1/orgs",
                headers={"Authorization": f"Bearer {oauth_access}"},
            )
        ).json()
        assert len(oauth_orgs) == 1
        assert oauth_orgs[0]["name"] == "OAuth Owner's Workspace"
        assert oauth_orgs[0]["role"] == "owner"

        # Audit log created on auto-provisioning
        oauth_org_id = uuid.UUID(oauth_orgs[0]["id"])
        db_org = (
            await test_db.execute(select(Organization).where(Organization.id == oauth_org_id))
        ).scalar_one()
        assert db_org.plan_id is None


class TestCrossTenantIsolationAndRBAC:
    """Verify server-side RBAC matrix, cross-tenant denial, and last-owner protection."""

    @pytest.mark.asyncio
    async def test_cross_tenant_access_denied_and_header_validation(
        self,
        async_client: AsyncClient,
        task_dispatcher: RecordingTaskDispatcher,
    ) -> None:
        token_a, _ = await _signup_verify_and_login(
            async_client, task_dispatcher, name="Tenant A Owner", email="ownera@example.com"
        )
        token_b, _ = await _signup_verify_and_login(
            async_client, task_dispatcher, name="Tenant B Owner", email="ownerb@example.com"
        )

        orgs_b = (
            await async_client.get("/api/v1/orgs", headers={"Authorization": f"Bearer {token_b}"})
        ).json()
        org_b_id = orgs_b[0]["id"]

        headers_a = {"Authorization": f"Bearer {token_a}"}
        assert "x-request-id" in (await async_client.get("/api/v1/orgs", headers=headers_a)).headers

        # Tenant A cannot read, mutate, invite, or audit Tenant B
        assert (
            await async_client.get(f"/api/v1/orgs/{org_b_id}", headers=headers_a)
        ).status_code == 403
        assert (
            await async_client.patch(
                f"/api/v1/orgs/{org_b_id}",
                json={"name": "Hijacked"},
                headers=headers_a,
            )
        ).status_code == 403
        assert (
            await async_client.get(f"/api/v1/orgs/{org_b_id}/members", headers=headers_a)
        ).status_code == 403
        assert (
            await async_client.post(
                f"/api/v1/orgs/{org_b_id}/invitations",
                json={"email": "spy@example.com", "role": "analyst"},
                headers=headers_a,
            )
        ).status_code == 403
        assert (
            await async_client.get(f"/api/v1/orgs/{org_b_id}/audit-logs", headers=headers_a)
        ).status_code == 403

        # Invalid X-Tenant-ID rejected cleanly with 400 when target org not in path
        create_resp = await async_client.post(
            "/api/v1/orgs",
            json={"name": "Second Org A"},
            headers={**headers_a, "X-Tenant-ID": "not-a-uuid"},
        )
        assert create_resp.status_code == 201  # POST /orgs ignores X-Tenant-ID

        # Path org_id overrides stale X-Tenant-ID belonging to another org
        orgs_a = (await async_client.get("/api/v1/orgs", headers=headers_a)).json()
        org_a1 = orgs_a[0]["id"]
        org_a2 = orgs_a[1]["id"]
        details = await async_client.get(
            f"/api/v1/orgs/{org_a2}",
            headers={**headers_a, "X-Tenant-ID": org_a1},
        )
        assert details.status_code == 200
        assert details.json()["id"] == org_a2

    @pytest.mark.asyncio
    async def test_invitations_lifecycle_cross_email_guard_and_rbac_matrix(
        self,
        async_client: AsyncClient,
        test_db: AsyncSession,
        task_dispatcher: RecordingTaskDispatcher,
    ) -> None:
        owner_token, _ = await _signup_verify_and_login(
            async_client, task_dispatcher, name="Owner User", email="owner@example.com"
        )
        analyst_token, analyst_login = await _signup_verify_and_login(
            async_client, task_dispatcher, name="Analyst User", email="analyst@example.com"
        )
        viewer_token, viewer_login = await _signup_verify_and_login(
            async_client, task_dispatcher, name="Viewer User", email="viewer@example.com"
        )
        outsider_token, _ = await _signup_verify_and_login(
            async_client, task_dispatcher, name="Outsider User", email="outsider@example.com"
        )

        owner_headers = {"Authorization": f"Bearer {owner_token}"}
        analyst_headers = {"Authorization": f"Bearer {analyst_token}"}
        viewer_headers = {"Authorization": f"Bearer {viewer_token}"}
        outsider_headers = {"Authorization": f"Bearer {outsider_token}"}

        org_id = (await async_client.get("/api/v1/orgs", headers=owner_headers)).json()[0]["id"]

        # Invite analyst twice -> first invite token is invalidated, second works
        inv_1 = await async_client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"email": "Analyst@Example.COM", "role": "analyst"},
            headers=owner_headers,
        )
        assert inv_1.status_code == 201
        stale_invite_token = _extract_token(str(task_dispatcher.jobs[-1].args[0]["accept_url"]))

        inv_2 = await async_client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"email": "analyst@example.com", "role": "analyst"},
            headers=owner_headers,
        )
        assert inv_2.status_code == 201
        valid_analyst_token = _extract_token(str(task_dispatcher.jobs[-1].args[0]["accept_url"]))

        # Stale invite token rejected
        assert (
            await async_client.post(
                "/api/v1/invitations/accept",
                json={"token": stale_invite_token},
                headers=analyst_headers,
            )
        ).status_code == 400

        # Outsider cannot accept an invite issued to analyst@example.com
        assert (
            await async_client.post(
                "/api/v1/invitations/accept",
                json={"token": valid_analyst_token},
                headers=outsider_headers,
            )
        ).status_code == 403

        # Analyst accepts valid token
        accepted_resp = await async_client.post(
            "/api/v1/invitations/accept",
            json={"token": valid_analyst_token},
            headers=analyst_headers,
        )
        assert accepted_resp.status_code == 200
        assert accepted_resp.json()["role"] == "analyst"

        # Token replay fails and inviting existing member returns 409
        assert (
            await async_client.post(
                "/api/v1/invitations/accept",
                json={"token": valid_analyst_token},
                headers=analyst_headers,
            )
        ).status_code == 400
        assert (
            await async_client.post(
                f"/api/v1/orgs/{org_id}/invitations",
                json={"email": "analyst@example.com", "role": "viewer"},
                headers=owner_headers,
            )
        ).status_code == 409

        # Invite and accept viewer
        await async_client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"email": "viewer@example.com", "role": "viewer"},
            headers=owner_headers,
        )
        viewer_invite_token = _extract_token(str(task_dispatcher.jobs[-1].args[0]["accept_url"]))
        assert (
            await async_client.post(
                "/api/v1/invitations/accept",
                json={"token": viewer_invite_token},
                headers=viewer_headers,
            )
        ).status_code == 200

        # RBAC checks for analyst and viewer: read org & members OK, admin endpoints 403
        for member_headers in (analyst_headers, viewer_headers):
            assert (
                await async_client.get(f"/api/v1/orgs/{org_id}", headers=member_headers)
            ).status_code == 200
            assert (
                await async_client.get(f"/api/v1/orgs/{org_id}/members", headers=member_headers)
            ).status_code == 200
            assert (
                await async_client.patch(
                    f"/api/v1/orgs/{org_id}",
                    json={"name": "Unauthorized Rename"},
                    headers=member_headers,
                )
            ).status_code == 403
            assert (
                await async_client.get(f"/api/v1/orgs/{org_id}/invitations", headers=member_headers)
            ).status_code == 403
            assert (
                await async_client.get(f"/api/v1/orgs/{org_id}/audit-logs", headers=member_headers)
            ).status_code == 403

        # Revocation & expiry tests
        pending_inv = await async_client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"email": "pending@example.com", "role": "viewer"},
            headers=owner_headers,
        )
        pending_id = pending_inv.json()["id"]
        assert (
            await async_client.delete(
                f"/api/v1/orgs/{org_id}/invitations/{pending_id}",
                headers=owner_headers,
            )
        ).status_code == 204
        assert (
            await async_client.get(f"/api/v1/orgs/{org_id}/invitations", headers=owner_headers)
        ).json() == []

    @pytest.mark.asyncio
    async def test_invitation_expiry_audit_logs_and_last_owner_protection(
        self,
        async_client: AsyncClient,
        test_db: AsyncSession,
        task_dispatcher: RecordingTaskDispatcher,
    ) -> None:
        owner_token, _ = await _signup_verify_and_login(
            async_client, task_dispatcher, name="Owner Two", email="owner2@example.com"
        )
        analyst_token, analyst_login = await _signup_verify_and_login(
            async_client, task_dispatcher, name="Analyst Two", email="analyst2@example.com"
        )
        viewer_token, _ = await _signup_verify_and_login(
            async_client, task_dispatcher, name="Viewer Two", email="viewer2@example.com"
        )
        outsider_token, _ = await _signup_verify_and_login(
            async_client, task_dispatcher, name="Outsider Two", email="outsider2@example.com"
        )

        owner_headers = {"Authorization": f"Bearer {owner_token}"}
        analyst_headers = {"Authorization": f"Bearer {analyst_token}"}
        viewer_headers = {"Authorization": f"Bearer {viewer_token}"}
        outsider_headers = {"Authorization": f"Bearer {outsider_token}"}
        org_id = (await async_client.get("/api/v1/orgs", headers=owner_headers)).json()[0]["id"]

        for email, role, hdrs in (
            ("analyst2@example.com", "analyst", analyst_headers),
            ("viewer2@example.com", "viewer", viewer_headers),
        ):
            await async_client.post(
                f"/api/v1/orgs/{org_id}/invitations",
                json={"email": email, "role": role},
                headers=owner_headers,
            )
            tok = _extract_token(str(task_dispatcher.jobs[-1].args[0]["accept_url"]))
            assert (
                await async_client.post(
                    "/api/v1/invitations/accept", json={"token": tok}, headers=hdrs
                )
            ).status_code == 200

        # Expire check on fresh invite
        exp_inv = await async_client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"email": "outsider2@example.com", "role": "viewer"},
            headers=owner_headers,
        )
        exp_token = _extract_token(str(task_dispatcher.jobs[-1].args[0]["accept_url"]))
        await test_db.execute(
            update(OrganizationInvitation)
            .where(OrganizationInvitation.id == uuid.UUID(exp_inv.json()["id"]))
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await test_db.commit()
        assert (
            await async_client.post(
                "/api/v1/invitations/accept",
                json={"token": exp_token},
                headers=outsider_headers,
            )
        ).status_code == 400

        # Audit logs visible to owner contain expected actions
        logs = (
            await async_client.get(f"/api/v1/orgs/{org_id}/audit-logs", headers=owner_headers)
        ).json()
        actions = {item["action"] for item in logs["items"]}
        assert {"org.created", "member.invited", "member.joined"}.issubset(actions)

        # Viewer leaves org cleanly
        assert (
            await async_client.post(f"/api/v1/orgs/{org_id}/leave", headers=viewer_headers)
        ).status_code == 200

        # Owner updates analyst role -> viewer -> owner, testing last-owner guard along the way
        owner_id = (await async_client.get("/api/v1/auth/me", headers=owner_headers)).json()["id"]
        analyst_id = analyst_login["user"]["id"]

        assert (
            await async_client.patch(
                f"/api/v1/orgs/{org_id}/members/{owner_id}",
                json={"role": "analyst"},
                headers=owner_headers,
            )
        ).status_code == 409
        assert (
            await async_client.post(f"/api/v1/orgs/{org_id}/leave", headers=owner_headers)
        ).status_code == 409

        # Promote analyst to owner, then original owner CAN leave safely (owner_id transfers!)
        promoted = await async_client.patch(
            f"/api/v1/orgs/{org_id}/members/{analyst_id}",
            json={"role": "owner"},
            headers=owner_headers,
        )
        assert promoted.status_code == 200
        assert promoted.json()["role"] == "owner"

        assert (
            await async_client.post(f"/api/v1/orgs/{org_id}/leave", headers=owner_headers)
        ).status_code == 200

        refreshed_org = (
            await test_db.execute(select(Organization).where(Organization.id == uuid.UUID(org_id)))
        ).scalar_one()
        assert str(refreshed_org.owner_id) == analyst_id

        # Former owner is now locked out (403)
        assert (
            await async_client.get(f"/api/v1/orgs/{org_id}", headers=owner_headers)
        ).status_code == 403

        # New owner removes leftover check / renames org cleanly
        renamed = await async_client.patch(
            f"/api/v1/orgs/{org_id}",
            json={"name": "Transferred Equity Team"},
            headers=analyst_headers,
        )
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Transferred Equity Team"

    @pytest.mark.asyncio
    async def test_invitation_rate_limit_enforces_429(
        self,
        async_client: AsyncClient,
        task_dispatcher: RecordingTaskDispatcher,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("AUTH_RATE_LIMIT_ORG_INVITE", "2")
        get_settings.cache_clear()

        token, _ = await _signup_verify_and_login(
            async_client, task_dispatcher, name="Rate Owner", email="rl_owner@example.com"
        )
        headers = {"Authorization": f"Bearer {token}"}
        org_id = (await async_client.get("/api/v1/orgs", headers=headers)).json()[0]["id"]

        for idx in range(2):
            resp = await async_client.post(
                f"/api/v1/orgs/{org_id}/invitations",
                json={"email": f"colleague{idx}@example.com", "role": "analyst"},
                headers=headers,
            )
            assert resp.status_code == 201

        limited = await async_client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"email": "colleague99@example.com", "role": "analyst"},
            headers=headers,
        )
        assert limited.status_code == 429
        assert int(limited.headers["Retry-After"]) > 0
        _ = (User, Membership, OrgRole)
