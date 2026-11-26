"""Real Redis 7 integration tests validating rate-limit Lua scripts atomically."""

import os
import uuid

import pytest
import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.rate_limit import (
    _FAILURE_CHECK_LUA,
    _FAILURE_RECORD_LUA,
    _TOKEN_BUCKET_LUA,
    _now_ms,
)

pytestmark = pytest.mark.integration


def _require_redis_integration_enabled() -> None:
    if os.getenv("FINSIGHT_RUN_REDIS_INTEGRATION") != "1":
        pytest.skip("Set FINSIGHT_RUN_REDIS_INTEGRATION=1 to run Redis Lua integration tests")


@pytest.mark.asyncio
async def test_real_redis_token_bucket_and_login_backoff_lua_scripts() -> None:
    """Execute actual rate-limit Lua scripts against Redis 7 server."""
    _require_redis_integration_enabled()

    get_settings.cache_clear()
    settings = get_settings()
    client = aioredis.from_url(str(settings.REDIS_URL), decode_responses=True)

    prefix = f"test:rl:{uuid.uuid4().hex}"
    tb_key = f"{prefix}:tb"
    pair_key = f"{prefix}:pair"
    ip_key = f"{prefix}:ip"
    dist_key = f"{prefix}:dist"

    try:
        now = _now_ms()
        # Token bucket: capacity=2, refill=2/900s
        res1 = await client.eval(
            _TOKEN_BUCKET_LUA, 1, tb_key, "2", "0.002222222", str(now), "60000"
        )  # type: ignore[misc]
        assert list(map(int, res1)) == [1, 1, 0]

        res2 = await client.eval(
            _TOKEN_BUCKET_LUA, 1, tb_key, "2", "0.002222222", str(now), "60000"
        )  # type: ignore[misc]
        assert list(map(int, res2)) == [1, 0, 0]

        res3 = await client.eval(
            _TOKEN_BUCKET_LUA, 1, tb_key, "2", "0.002222222", str(now), "60000"
        )  # type: ignore[misc]
        assert int(res3[0]) == 0
        assert int(res3[2]) >= 400

        # Login failure progression & cooldown check on real Redis
        for idx in range(1, 6):
            rec = await client.eval(  # type: ignore[misc]
                _FAILURE_RECORD_LUA, 1, pair_key, "5", "900000", str(now), "5", "15", "60", "300"
            )
            assert int(rec[0]) == idx
            if idx < 5:
                assert int(rec[2]) == 0
            else:
                assert int(rec[2]) == 5

        chk = await client.eval(  # type: ignore[misc]
            _FAILURE_CHECK_LUA, 3, pair_key, ip_key, dist_key, str(now)
        )
        assert 1 <= int(chk[0]) <= 5
        assert int(chk[1]) == 1

        # Expiry elapsed -> cooldown no longer blocks
        chk_expired = await client.eval(  # type: ignore[misc]
            _FAILURE_CHECK_LUA, 3, pair_key, ip_key, dist_key, str(now + 6000)
        )
        assert list(map(int, chk_expired)) == [0, 0]
    finally:
        await client.delete(tb_key, pair_key, ip_key, dist_key)
        await client.aclose()
