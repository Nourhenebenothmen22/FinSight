"""Integration tests for F1 /api/v1/auth endpoints."""

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.auth import AuthToken, RefreshToken, User
from app.services import auth as auth_service
from tests.conftest import RecordingTaskDispatcher

_PASSWORD_1 = "Strong!Pass2026#"
_PASSWORD_2 = "Newer!Pass2026$"


def _extract_token_from_url(url: str) -> str:
    query = parse_qs(urlparse(url).query)
    return query["token"][0]


async def _register_and_verify(
    async_client: AsyncClient,
    dispatcher: RecordingTaskDispatcher,
    *,
    email: str = "alice@example.com",
    name: str = "Alice Analyst",
    password: str = _PASSWORD_1,
) -> dict[str, Any]:
    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": password},
    )
    assert reg_resp.status_code == 201
    assert len(dispatcher.jobs) >= 1
    job = dispatcher.jobs[-1]
    assert job.task_name == "send_verification_email_task"
    raw_token = _extract_token_from_url(str(job.args[2]))

    verify_resp = await async_client.post("/api/v1/auth/verify", json={"token": raw_token})
    assert verify_resp.status_code == 200
    result: dict[str, Any] = reg_resp.json()
    return result


class TestRegistrationAndEmailVerification:
    """Test user registration, Argon2id storage, verification tokens, and resending."""

    @pytest.mark.asyncio
    async def test_register_requires_verification_before_login(
        self,
        async_client: AsyncClient,
        test_db: AsyncSession,
        task_dispatcher: RecordingTaskDispatcher,
    ) -> None:
        reg_resp = await async_client.post(
            "/api/v1/auth/register",
            json={
                "name": "Bob Investor",
                "email": "Bob@Example.COM",
                "password": _PASSWORD_1,
            },
        )
        assert reg_resp.status_code == 201
        data = reg_resp.json()
        assert data["user"]["email"] == "bob@example.com"
        assert data["user"]["email_verified_at"] is None
        assert data["user"]["has_password"] is True
        assert "password_hash" not in data["user"]

        # Stored with Argon2id
        user_row = (
            await test_db.execute(select(User).where(User.email == "bob@example.com"))
        ).scalar_one()
        assert user_row.password_hash is not None
        assert user_row.password_hash.startswith("$argon2id$")

        # Wrong password still returns 401 (does not disclose verification state)
        bad_login = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "bob@example.com", "password": "Wrong!Password1"},
        )
        assert bad_login.status_code == 401

        # Correct password before email verification returns 403
        unverified_login = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "bob@example.com", "password": _PASSWORD_1},
        )
        assert unverified_login.status_code == 403

        # Resending invalidates prior token; only latest token works
        first_token = _extract_token_from_url(str(task_dispatcher.jobs[0].args[2]))
        resend_resp = await async_client.post(
            "/api/v1/auth/resend-verification",
            json={"email": "bob@example.com"},
        )
        assert resend_resp.status_code == 202
        second_token = _extract_token_from_url(str(task_dispatcher.jobs[1].args[2]))
        assert first_token != second_token

        stale_verify = await async_client.post("/api/v1/auth/verify", json={"token": first_token})
        assert stale_verify.status_code == 400

        ok_verify = await async_client.post("/api/v1/auth/verify", json={"token": second_token})
        assert ok_verify.status_code == 200

        # Single-use token cannot be replayed
        replay_verify = await async_client.post("/api/v1/auth/verify", json={"token": second_token})
        assert replay_verify.status_code == 400

        # Login succeeds after verification
        login_resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "bob@example.com", "password": _PASSWORD_1},
        )
        assert login_resp.status_code == 200
        assert login_resp.json()["user"]["email_verified_at"] is not None

    @pytest.mark.asyncio
    async def test_duplicate_email_returns_409_and_resend_unknown_is_uniform_202(
        self,
        async_client: AsyncClient,
        task_dispatcher: RecordingTaskDispatcher,
    ) -> None:
        await _register_and_verify(async_client, task_dispatcher, email="dup@example.com")

        dup_resp = await async_client.post(
            "/api/v1/auth/register",
            json={"name": "Another", "email": "DUP@example.com", "password": _PASSWORD_1},
        )
        assert dup_resp.status_code == 409

        unknown_resend = await async_client.post(
            "/api/v1/auth/resend-verification",
            json={"email": "nobody@example.com"},
        )
        assert unknown_resend.status_code == 202


class TestLoginRefreshRotationAndLogout:
    """Test JWT login, cookie transport, refresh rotation, reuse detection, and CSRF."""

    @pytest.mark.asyncio
    async def test_refresh_rotation_and_reuse_detection_revokes_family(
        self,
        async_client: AsyncClient,
        test_db: AsyncSession,
        task_dispatcher: RecordingTaskDispatcher,
    ) -> None:
        await _register_and_verify(async_client, task_dispatcher, email="rot@example.com")

        login_resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "rot@example.com", "password": _PASSWORD_1},
        )
        assert login_resp.status_code == 200
        tokens_1 = login_resp.json()
        refresh_1 = tokens_1["refresh_token"]
        access_1 = tokens_1["access_token"]
        assert refresh_1
        assert "finsight_refresh_token" in login_resp.cookies

        # Access token works on /me, cannot be used on /refresh
        me_resp = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_1}"},
        )
        assert me_resp.status_code == 200

        bad_refresh = await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": access_1},
        )
        assert bad_refresh.status_code == 401

        # Refresh token cannot be used on /me
        bad_me = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {refresh_1}"},
        )
        assert bad_me.status_code == 401

        # Cookie-based empty-body refresh rotates token cleanly
        refresh_resp = await async_client.post("/api/v1/auth/refresh")
        assert refresh_resp.status_code == 200
        refresh_2 = refresh_resp.json()["refresh_token"]
        assert refresh_2 != refresh_1

        # Reuse attack: replaying old refresh_1 MUST trigger 401 AND revoke family (including refresh_2!)
        reuse_resp = await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_1},
        )
        assert reuse_resp.status_code == 401

        after_reuse = await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_2},
        )
        assert after_reuse.status_code == 401

        family_rows = (await test_db.execute(select(RefreshToken))).scalars().all()
        assert len(family_rows) == 2
        assert all(row.revoked_at is not None for row in family_rows)

    @pytest.mark.asyncio
    async def test_cookie_csrf_origin_check_and_logout(
        self,
        async_client: AsyncClient,
        task_dispatcher: RecordingTaskDispatcher,
    ) -> None:
        await _register_and_verify(async_client, task_dispatcher, email="csrf@example.com")
        login_resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "csrf@example.com", "password": _PASSWORD_1},
        )
        assert login_resp.status_code == 200

        # Cross-site cookie refresh blocked with 403
        cross_site = await async_client.post(
            "/api/v1/auth/refresh",
            headers={"Origin": "https://attacker.example"},
        )
        assert cross_site.status_code == 403

        # Same-origin logout succeeds and clears cookie
        logout_resp = await async_client.post(
            "/api/v1/auth/logout",
            headers={"Origin": "http://localhost:3000"},
        )
        assert logout_resp.status_code == 200

        post_logout_refresh = await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login_resp.json()["refresh_token"]},
        )
        assert post_logout_refresh.status_code == 401


class TestPasswordResetAndProfileManagement:
    """Test forgot/reset password, session management, profile updates, and active guard."""

    @pytest.mark.asyncio
    async def test_forgot_and_reset_revokes_existing_sessions(
        self,
        async_client: AsyncClient,
        test_db: AsyncSession,
        task_dispatcher: RecordingTaskDispatcher,
    ) -> None:
        await _register_and_verify(async_client, task_dispatcher, email="reset@example.com")
        login_resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "reset@example.com", "password": _PASSWORD_1},
        )
        old_refresh = login_resp.json()["refresh_token"]

        # Forgot is uniform 202 for unknown and existing users
        unknown_forgot = await async_client.post(
            "/api/v1/auth/forgot",
            json={"email": "nonexistent@example.com"},
        )
        assert unknown_forgot.status_code == 202

        known_forgot = await async_client.post(
            "/api/v1/auth/forgot",
            json={"email": "reset@example.com"},
        )
        assert known_forgot.status_code == 202
        reset_job = task_dispatcher.jobs[-1]
        assert reset_job.task_name == "send_password_reset_email_task"
        reset_token = _extract_token_from_url(str(reset_job.args[2]))

        reset_resp = await async_client.post(
            "/api/v1/auth/reset",
            json={"token": reset_token, "new_password": _PASSWORD_2},
        )
        assert reset_resp.status_code == 200

        # Replay of reset token fails
        replay = await async_client.post(
            "/api/v1/auth/reset",
            json={"token": reset_token, "new_password": _PASSWORD_2},
        )
        assert replay.status_code == 400

        # Old password fails; old refresh token revoked; new password works
        assert (
            await async_client.post(
                "/api/v1/auth/login",
                json={"email": "reset@example.com", "password": _PASSWORD_1},
            )
        ).status_code == 401
        assert (
            await async_client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": old_refresh},
            )
        ).status_code == 401
        assert (
            await async_client.post(
                "/api/v1/auth/login",
                json={"email": "reset@example.com", "password": _PASSWORD_2},
            )
        ).status_code == 200

        # Expired token test
        user = (
            await test_db.execute(select(User).where(User.email == "reset@example.com"))
        ).scalar_one()
        await async_client.post("/api/v1/auth/forgot", json={"email": "reset@example.com"})
        expired_token = _extract_token_from_url(str(task_dispatcher.jobs[-1].args[2]))
        await test_db.execute(
            update(AuthToken)
            .where(AuthToken.user_id == user.id, AuthToken.purpose == "password_reset")
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=5))
        )
        await test_db.commit()
        expired_resp = await async_client.post(
            "/api/v1/auth/reset",
            json={"token": expired_token, "new_password": _PASSWORD_1},
        )
        assert expired_resp.status_code == 400

    @pytest.mark.asyncio
    async def test_profile_update_change_password_and_sessions(
        self,
        async_client: AsyncClient,
        test_db: AsyncSession,
        task_dispatcher: RecordingTaskDispatcher,
    ) -> None:
        await _register_and_verify(async_client, task_dispatcher, email="prof@example.com")
        # Create two distinct sessions
        login_1 = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "prof@example.com", "password": _PASSWORD_1},
        )
        refresh_1 = login_1.json()["refresh_token"]
        login_2 = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "prof@example.com", "password": _PASSWORD_1},
        )
        access_2 = login_2.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {access_2}"}

        # Update name
        patch_resp = await async_client.patch(
            "/api/v1/auth/me",
            json={"name": "Alice Senior Analyst"},
            headers=auth_headers,
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["name"] == "Alice Senior Analyst"

        # List sessions shows 2 active
        sessions_resp = await async_client.get("/api/v1/auth/sessions", headers=auth_headers)
        assert sessions_resp.status_code == 200
        sessions = sessions_resp.json()
        assert len(sessions) == 2

        # Wrong current password rejected
        bad_cp = await async_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "WrongPassword!99", "new_password": _PASSWORD_2},
            headers=auth_headers,
        )
        assert bad_cp.status_code == 400

        # Valid change password revokes other session (refresh_1), keeps current session alive
        ok_cp = await async_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": _PASSWORD_1, "new_password": _PASSWORD_2},
            headers=auth_headers,
        )
        assert ok_cp.status_code == 200

        assert (
            await async_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_1})
        ).status_code == 401
        assert (await async_client.post("/api/v1/auth/refresh")).status_code == 200

        # Logout all revokes remaining sessions
        assert (
            await async_client.post("/api/v1/auth/logout-all", headers=auth_headers)
        ).status_code == 200
        assert (await async_client.get("/api/v1/auth/sessions", headers=auth_headers)).json() == []

        # Deactivated user blocked from /me
        await test_db.execute(
            update(User).where(User.email == "prof@example.com").values(is_active=False)
        )
        await test_db.commit()
        assert (await async_client.get("/api/v1/auth/me", headers=auth_headers)).status_code == 403


class TestGoogleOAuthAndRateLimiting:
    """Test Google OAuth PKCE/state/JWKS flow, pre-hijacking defense, and Redis rate limiting."""

    @pytest.mark.asyncio
    async def test_google_login_returns_503_when_unconfigured(
        self, async_client: AsyncClient
    ) -> None:
        resp = await async_client.get("/api/v1/auth/google/login", follow_redirects=False)
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_google_oauth_tampered_state_and_pre_hijacking_protection(
        self,
        async_client: AsyncClient,
        task_dispatcher: RecordingTaskDispatcher,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client-id-123")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-client-secret-456")
        get_settings.cache_clear()

        login_resp = await async_client.get(
            "/api/v1/auth/google/login?next=/profile",
            follow_redirects=False,
        )
        assert login_resp.status_code == 302
        location = login_resp.headers["location"]
        parsed_google = urlparse(location)
        assert parsed_google.netloc == "accounts.google.com"
        params = parse_qs(parsed_google.query)
        state = params["state"][0]
        assert params["code_challenge_method"][0] == "S256"

        tampered_cb = await async_client.get(
            "/api/v1/auth/google/callback?code=fake&state=wrong-state",
            follow_redirects=False,
        )
        assert tampered_cb.status_code == 302
        assert "oauth_error=invalid_state" in tampered_cb.headers["location"]

        # Start a new OAuth handshake after the previous callback cleared the state cookie
        fresh_login = await async_client.get(
            "/api/v1/auth/google/login?next=/profile",
            follow_redirects=False,
        )
        state = parse_qs(urlparse(fresh_login.headers["location"]).query)["state"][0]

        await async_client.post(
            "/api/v1/auth/register",
            json={
                "name": "Pending User",
                "email": "conflict@example.com",
                "password": _PASSWORD_1,
            },
        )
        _ = task_dispatcher

        async def fake_exchange(**kwargs: Any) -> dict[str, Any]:
            _ = kwargs
            return {"id_token": "mock-id-token"}

        async def fake_verify_conflict(**kwargs: Any) -> dict[str, Any]:
            _ = kwargs
            return {
                "sub": "google-sub-conflict",
                "email": "conflict@example.com",
                "email_verified": True,
                "name": "Pending User",
            }

        monkeypatch.setattr(auth_service, "exchange_google_authorization_code", fake_exchange)
        monkeypatch.setattr(auth_service, "verify_google_id_token", fake_verify_conflict)

        conflict_cb = await async_client.get(
            f"/api/v1/auth/google/callback?code=auth-code-1&state={state}",
            follow_redirects=False,
        )
        assert conflict_cb.status_code == 302
        assert "oauth_error=email_unverified_conflict" in conflict_cb.headers["location"]

    @pytest.mark.asyncio
    async def test_google_oauth_new_user_exchange_and_set_password(
        self,
        async_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client-id-123")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-client-secret-456")
        get_settings.cache_clear()

        login_resp = await async_client.get(
            "/api/v1/auth/google/login?next=/profile",
            follow_redirects=False,
        )
        state = parse_qs(urlparse(login_resp.headers["location"]).query)["state"][0]

        async def fake_exchange(**kwargs: Any) -> dict[str, Any]:
            _ = kwargs
            return {"id_token": "mock-id-token"}

        async def fake_verify_new(**kwargs: Any) -> dict[str, Any]:
            _ = kwargs
            return {
                "sub": "google-sub-new-user",
                "email": "oauth.user@example.com",
                "email_verified": True,
                "name": "OAuth User",
            }

        monkeypatch.setattr(auth_service, "exchange_google_authorization_code", fake_exchange)
        monkeypatch.setattr(auth_service, "verify_google_id_token", fake_verify_new)

        ok_cb = await async_client.get(
            f"/api/v1/auth/google/callback?code=auth-code-2&state={state}",
            follow_redirects=False,
        )
        assert ok_cb.status_code == 302
        cb_loc = ok_cb.headers["location"]
        assert "/auth/google/callback?code=" in cb_loc
        assert "access_token" not in cb_loc
        assert "refresh_token" not in cb_loc

        exchange_code = parse_qs(urlparse(cb_loc).query)["code"][0]
        ex_resp = await async_client.post(
            "/api/v1/auth/google/exchange",
            json={"code": exchange_code},
        )
        assert ex_resp.status_code == 200
        ex_data = ex_resp.json()
        assert ex_data["user"]["email"] == "oauth.user@example.com"
        assert ex_data["user"]["oauth_provider"] == "google"
        assert ex_data["user"]["has_password"] is False
        assert ex_data["next_path"] == "/profile"
        assert "finsight_refresh_token" in ex_resp.cookies

        replay_ex = await async_client.post(
            "/api/v1/auth/google/exchange",
            json={"code": exchange_code},
        )
        assert replay_ex.status_code == 401

        assert (
            await async_client.post(
                "/api/v1/auth/login",
                json={"email": "oauth.user@example.com", "password": _PASSWORD_1},
            )
        ).status_code == 401

        set_pw = await async_client.post(
            "/api/v1/auth/change-password",
            json={"new_password": _PASSWORD_1},
            headers={"Authorization": f"Bearer {ex_data['access_token']}"},
        )
        assert set_pw.status_code == 200

        assert (
            await async_client.post(
                "/api/v1/auth/login",
                json={"email": "oauth.user@example.com", "password": _PASSWORD_1},
            )
        ).status_code == 200

    @pytest.mark.asyncio
    async def test_rate_limiter_enforces_429_and_retry_after(
        self,
        async_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("AUTH_RATE_LIMIT_FORGOT", "2")
        get_settings.cache_clear()

        for _ in range(2):
            resp = await async_client.post(
                "/api/v1/auth/forgot",
                json={"email": "ratelimit@example.com"},
            )
            assert resp.status_code == 202

        limited = await async_client.post(
            "/api/v1/auth/forgot",
            json={"email": "ratelimit@example.com"},
        )
        assert limited.status_code == 429
        assert int(limited.headers["Retry-After"]) > 0
