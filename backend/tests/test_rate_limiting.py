"""Comprehensive unit & adversarial tests for hybrid rate limiting and backoff."""

from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient

from app.core import rate_limit
from app.core.config import get_settings
from app.services import auth as auth_service
from tests.conftest import RecordingTaskDispatcher

_PASSWORD = "Strong!Pass2026#Valid"


def _extract_token(url: str) -> str:
    return parse_qs(urlparse(url).query)["token"][0]


async def _register_verify(
    async_client: AsyncClient,
    dispatcher: RecordingTaskDispatcher,
    *,
    name: str,
    email: str,
) -> None:
    reg = await async_client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": _PASSWORD},
    )
    assert reg.status_code == 201
    token = _extract_token(str(dispatcher.jobs[-1].args[2]))
    ver = await async_client.post("/api/v1/auth/verify", json={"token": token})
    assert ver.status_code == 200


class TestHybridRateLimiting:
    """Validate Option B hybrid Token Bucket, login failure backoff, and actor isolation."""

    @pytest.mark.asyncio
    async def test_unlimited_valid_logins_never_trigger_429(
        self,
        async_client: AsyncClient,
        task_dispatcher: RecordingTaskDispatcher,
    ) -> None:
        await _register_verify(
            async_client, task_dispatcher, name="Repeat User", email="repeat@example.com"
        )

        for _ in range(15):
            resp = await async_client.post(
                "/api/v1/auth/login",
                json={"email": "repeat@example.com", "password": _PASSWORD},
            )
            assert resp.status_code == 200
            assert "access_token" in resp.json()

    @pytest.mark.asyncio
    async def test_login_progressive_backoff_skips_argon2_during_cooldown_and_resets_on_success(
        self,
        async_client: AsyncClient,
        task_dispatcher: RecordingTaskDispatcher,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Raise IP spray threshold so this test isolates the per-(ip, email) pair progression
        monkeypatch.setenv("AUTH_RATE_LIMIT_LOGIN_IP", "25")
        get_settings.cache_clear()

        await _register_verify(
            async_client, task_dispatcher, name="Backoff User", email="backoff@example.com"
        )

        clock_ms = 1_700_000_000_000
        monkeypatch.setattr(rate_limit, "_now_ms", lambda: clock_ms)

        # Failures 1..5 tolerated (401); 5th arms initial 5s cooldown
        for _ in range(5):
            bad = await async_client.post(
                "/api/v1/auth/login",
                json={"email": "backoff@example.com", "password": "Wrong!Password99"},
            )
            assert bad.status_code == 401

        # Verify Argon2id is NOT invoked while cooldown is active
        argon_calls = 0
        orig_verify = auth_service.verify_password_constant_time

        def tracked_verify(plain: str, hashed: str | None) -> bool:
            nonlocal argon_calls
            argon_calls += 1
            return orig_verify(plain, hashed)

        monkeypatch.setattr(auth_service, "verify_password_constant_time", tracked_verify)

        blocked_5 = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "backoff@example.com", "password": _PASSWORD},
        )
        assert blocked_5.status_code == 429
        assert blocked_5.headers["Retry-After"] == "5"
        assert argon_calls == 0

        # Escalate through 15s -> 60s -> 300s tiers
        expected_tiers = [(6_000, "15"), (16_000, "60"), (61_000, "300")]
        for advance_ms, expected_retry in expected_tiers:
            clock_ms += advance_ms
            fail_resp = await async_client.post(
                "/api/v1/auth/login",
                json={"email": "backoff@example.com", "password": "Wrong!Password99"},
            )
            assert fail_resp.status_code == 401

            blocked = await async_client.post(
                "/api/v1/auth/login",
                json={"email": "backoff@example.com", "password": "Wrong!Password99"},
            )
            assert blocked.status_code == 429
            assert blocked.headers["Retry-After"] == expected_retry

        # Wait past 300s and log in validly -> resets (ip, email) failure streak
        clock_ms += 301_000
        ok = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "backoff@example.com", "password": _PASSWORD},
        )
        assert ok.status_code == 200

        # Next wrong attempts get a fresh 5 tolerated failures again before 5s backoff
        for _ in range(4):
            fresh_bad = await async_client.post(
                "/api/v1/auth/login",
                json={"email": "backoff@example.com", "password": "Wrong!Password99"},
            )
            assert fresh_bad.status_code == 401

    @pytest.mark.asyncio
    async def test_attacker_cannot_lockout_victim_and_distributed_cap_blocks_stuffing(
        self,
        async_client: AsyncClient,
        task_dispatcher: RecordingTaskDispatcher,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("AUTH_LOGIN_DISTRIBUTED_EMAIL_LIMIT", "8")
        get_settings.cache_clear()

        await _register_verify(
            async_client, task_dispatcher, name="Victim User", email="victim@example.com"
        )

        # Attacker on IP B hits backoff against victim@example.com
        for _ in range(5):
            assert (
                await async_client.post(
                    "/api/v1/auth/login",
                    json={"email": "victim@example.com", "password": "Wrong!Password99"},
                    headers={"X-Forwarded-For": "198.51.100.50"},
                )
            ).status_code == 401
        assert (
            await async_client.post(
                "/api/v1/auth/login",
                json={"email": "victim@example.com", "password": "Wrong!Password99"},
                headers={"X-Forwarded-For": "198.51.100.50"},
            )
        ).status_code == 429

        # Victim on IP A is completely unaffected and logs in cleanly
        victim_ok = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "victim@example.com", "password": _PASSWORD},
            headers={"X-Forwarded-For": "203.0.113.10"},
        )
        assert victim_ok.status_code == 200

        # Distributed stuffing: 8 distinct attacker IPs fail once each -> 9th IP gets 429
        for idx in range(8):
            await async_client.post(
                "/api/v1/auth/login",
                json={"email": "stuffed@example.com", "password": "Wrong!Password99"},
                headers={"X-Forwarded-For": f"198.51.100.{100 + idx}"},
            )

        stuffed_blocked = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "stuffed@example.com", "password": "Wrong!Password99"},
            headers={"X-Forwarded-For": "198.51.100.250"},
        )
        assert stuffed_blocked.status_code == 429
        assert int(stuffed_blocked.headers["Retry-After"]) >= 60

    @pytest.mark.asyncio
    async def test_relaxed_dev_profile_allows_burst_and_keeps_short_5s_backoff(
        self,
        async_client: AsyncClient,
        task_dispatcher: RecordingTaskDispatcher,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("RATE_LIMIT_PROFILE", "auto")
        monkeypatch.setenv("RATE_LIMIT_DEV_BURST", "20")
        monkeypatch.setenv("RATE_LIMIT_DEV_BACKOFF_SECONDS", "5")
        get_settings.cache_clear()

        clock_ms = 1_700_000_000_000
        monkeypatch.setattr(rate_limit, "_now_ms", lambda: clock_ms)

        # Register burst up to 20 passes without blocking dev QA, then 21st still triggers 429
        for idx in range(20):
            resp = await async_client.post(
                "/api/v1/auth/register",
                json={
                    "name": f"Dev {idx}",
                    "email": f"dev{idx}@example.com",
                    "password": _PASSWORD,
                },
            )
            assert resp.status_code == 201
            assert resp.headers["X-RateLimit-Limit"] == "20"

        burst_limited = await async_client.post(
            "/api/v1/auth/register",
            json={"name": "Dev 21", "email": "dev21@example.com", "password": _PASSWORD},
        )
        assert burst_limited.status_code == 429

        # In relaxed_dev, repeat login cooldown stays short (5s even on subsequent failure)
        token = _extract_token(str(task_dispatcher.jobs[0].args[2]))
        await async_client.post("/api/v1/auth/verify", json={"token": token})

        for _ in range(5):
            assert (
                await async_client.post(
                    "/api/v1/auth/login",
                    json={"email": "dev0@example.com", "password": "Wrong!Password99"},
                )
            ).status_code == 401
        first_cd = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "dev0@example.com", "password": "Wrong!Password99"},
        )
        assert first_cd.status_code == 429
        assert first_cd.headers["Retry-After"] == "5"

        clock_ms += 6_000
        assert (
            await async_client.post(
                "/api/v1/auth/login",
                json={"email": "dev0@example.com", "password": "Wrong!Password99"},
            )
        ).status_code == 401
        second_cd = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "dev0@example.com", "password": "Wrong!Password99"},
        )
        assert second_cd.status_code == 429
        assert second_cd.headers["Retry-After"] == "5"

    @pytest.mark.asyncio
    async def test_actor_rate_limits_isolate_tenants_behind_shared_nat_and_preserve_403(
        self,
        async_client: AsyncClient,
        task_dispatcher: RecordingTaskDispatcher,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("AUTH_RATE_LIMIT_ORG_INVITE", "2")
        get_settings.cache_clear()

        await _register_verify(
            async_client, task_dispatcher, name="Owner A", email="ownera@example.com"
        )
        await _register_verify(
            async_client, task_dispatcher, name="Owner B", email="ownerb@example.com"
        )
        await _register_verify(
            async_client, task_dispatcher, name="Viewer C", email="viewerc@example.com"
        )

        shared_ip = {"X-Forwarded-For": "203.0.113.55"}
        tok_a = (
            await async_client.post(
                "/api/v1/auth/login",
                json={"email": "ownera@example.com", "password": _PASSWORD},
                headers=shared_ip,
            )
        ).json()["access_token"]
        tok_b = (
            await async_client.post(
                "/api/v1/auth/login",
                json={"email": "ownerb@example.com", "password": _PASSWORD},
                headers=shared_ip,
            )
        ).json()["access_token"]
        tok_c = (
            await async_client.post(
                "/api/v1/auth/login",
                json={"email": "viewerc@example.com", "password": _PASSWORD},
                headers=shared_ip,
            )
        ).json()["access_token"]

        org_a = (
            await async_client.get("/api/v1/orgs", headers={"Authorization": f"Bearer {tok_a}"})
        ).json()[0]["id"]
        org_b = (
            await async_client.get("/api/v1/orgs", headers={"Authorization": f"Bearer {tok_b}"})
        ).json()[0]["id"]

        # Invite Viewer C into org_a as viewer
        inv_c = await async_client.post(
            f"/api/v1/orgs/{org_a}/invitations",
            json={"email": "viewerc@example.com", "role": "viewer"},
            headers={"Authorization": f"Bearer {tok_a}", **shared_ip},
        )
        assert inv_c.status_code == 201
        c_token = _extract_token(str(task_dispatcher.jobs[-1].args[0]["accept_url"]))
        await async_client.post(
            "/api/v1/invitations/accept",
            json={"token": c_token},
            headers={"Authorization": f"Bearer {tok_c}", **shared_ip},
        )

        # Viewer C attempting owner-only POST /invitations always gets 403 (never 429 or consuming A's quota)
        for _ in range(4):
            denied = await async_client.post(
                f"/api/v1/orgs/{org_a}/invitations",
                json={"email": "x@example.com", "role": "analyst"},
                headers={"Authorization": f"Bearer {tok_c}", **shared_ip},
            )
            assert denied.status_code == 403

        # Owner A uses 2nd invite quota then hits 429
        assert (
            await async_client.post(
                f"/api/v1/orgs/{org_a}/invitations",
                json={"email": "d@example.com", "role": "analyst"},
                headers={"Authorization": f"Bearer {tok_a}", **shared_ip},
            )
        ).status_code == 201
        assert (
            await async_client.post(
                f"/api/v1/orgs/{org_a}/invitations",
                json={"email": "e@example.com", "role": "analyst"},
                headers={"Authorization": f"Bearer {tok_a}", **shared_ip},
            )
        ).status_code == 429

        # Owner B on the exact same NAT IP still has full quota
        ok_b = await async_client.post(
            f"/api/v1/orgs/{org_b}/invitations",
            json={"email": "f@example.com", "role": "analyst"},
            headers={"Authorization": f"Bearer {tok_b}", **shared_ip},
        )
        assert ok_b.status_code == 201
        assert ok_b.headers["X-RateLimit-Limit"] == "2"
        assert ok_b.headers["X-RateLimit-Remaining"] == "1"

    @pytest.mark.asyncio
    async def test_token_bucket_refills_smoothly_and_exposes_rate_headers(
        self,
        async_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("AUTH_RATE_LIMIT_FORGOT", "2")
        get_settings.cache_clear()

        clock_ms = 1_700_000_000_000
        monkeypatch.setattr(rate_limit, "_now_ms", lambda: clock_ms)

        r1 = await async_client.post("/api/v1/auth/forgot", json={"email": "smooth@example.com"})
        assert r1.status_code == 202
        assert r1.headers["X-RateLimit-Limit"] == "2"
        assert r1.headers["X-RateLimit-Remaining"] == "1"

        r2 = await async_client.post("/api/v1/auth/forgot", json={"email": "smooth@example.com"})
        assert r2.status_code == 202
        assert r2.headers["X-RateLimit-Remaining"] == "0"

        r3 = await async_client.post("/api/v1/auth/forgot", json={"email": "smooth@example.com"})
        assert r3.status_code == 429
        assert 450 <= int(r3.headers["Retry-After"]) <= 451

        # Advance 451s (half of 900s window -> 1 token refilled, not locked out for full 900s)
        clock_ms += 451_000
        r4 = await async_client.post("/api/v1/auth/forgot", json={"email": "smooth@example.com"})
        assert r4.status_code == 202
