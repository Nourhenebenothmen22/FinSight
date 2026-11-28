"""Redis-backed multi-policy rate limiting with Token Bucket and progressive login backoff."""

import ipaddress
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, NoReturn

import redis.asyncio as aioredis
import structlog
from fastapi import Depends, HTTPException, Request, Response, status

from app.core.config import Settings, get_settings
from app.core.redis import get_redis
from app.core.security import hash_token

logger = structlog.get_logger(__name__)

# Token bucket stored as "<tokens>:<last_ms>" with millisecond TTL.
_TOKEN_BUCKET_LUA = """
-- FINSIGHT_LUA:token_bucket
local raw = redis.call("GET", KEYS[1])
local capacity = tonumber(ARGV[1])
local refill_per_sec = tonumber(ARGV[2])
local now_ms = tonumber(ARGV[3])
local ttl_ms = tonumber(ARGV[4])
local tokens = capacity
local last_ms = now_ms

if raw then
  local sep = string.find(raw, ":", 1, true)
  if sep then
    tokens = tonumber(string.sub(raw, 1, sep - 1)) or capacity
    last_ms = tonumber(string.sub(raw, sep + 1)) or now_ms
  end
end

local elapsed = math.max(0, (now_ms - last_ms) / 1000.0)
tokens = math.min(capacity, tokens + elapsed * refill_per_sec)

if tokens >= 1.0 then
  tokens = tokens - 1.0
  redis.call("SET", KEYS[1], string.format("%.9f:%d", tokens, now_ms), "PX", ttl_ms)
  return {1, math.floor(tokens), 0}
end

local needed = 1.0 - tokens
local retry_after = math.max(1, math.ceil(needed / refill_per_sec))
redis.call("SET", KEYS[1], string.format("%.9f:%d", tokens, now_ms), "PX", ttl_ms)
return {0, 0, retry_after}
"""

# Read-only check across multiple login failure buckets: "<count>:<blocked_until_ms>".
_FAILURE_CHECK_LUA = """
-- FINSIGHT_LUA:login_cooldown_check
local now_ms = tonumber(ARGV[1])
local max_retry_sec = 0
local blocking_idx = 0

for i = 1, #KEYS do
  local raw = redis.call("GET", KEYS[i])
  if raw then
    local sep = string.find(raw, ":", 1, true)
    if sep then
      local blocked_until = tonumber(string.sub(raw, sep + 1)) or 0
      if blocked_until > now_ms then
        local retry_sec = math.max(1, math.ceil((blocked_until - now_ms) / 1000.0))
        if retry_sec > max_retry_sec then
          max_retry_sec = retry_sec
          blocking_idx = i
        end
      end
    end
  end
end

return {max_retry_sec, blocking_idx}
"""

# Failure counter with progressive backoff tiers stored as "<count>:<blocked_until_ms>".
_FAILURE_RECORD_LUA = """
-- FINSIGHT_LUA:login_failure
local raw = redis.call("GET", KEYS[1])
local free_attempts = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local now_ms = tonumber(ARGV[3])
local count = 0
local blocked_until_ms = 0

if raw then
  local sep = string.find(raw, ":", 1, true)
  if sep then
    count = tonumber(string.sub(raw, 1, sep - 1)) or 0
    blocked_until_ms = tonumber(string.sub(raw, sep + 1)) or 0
  end
end

count = count + 1
local penalty_sec = 0
if count >= free_attempts then
  local num_steps = #ARGV - 3
  if num_steps > 0 then
    local step_idx = count - free_attempts + 1
    if step_idx > num_steps then
      step_idx = num_steps
    end
    penalty_sec = tonumber(ARGV[3 + step_idx]) or 0
    local candidate_until = now_ms + penalty_sec * 1000
    if candidate_until > blocked_until_ms then
      blocked_until_ms = candidate_until
    end
  end
end

local ttl_ms = math.max(window_ms, penalty_sec * 1000 + 1000)
redis.call("SET", KEYS[1], string.format("%d:%d", count, blocked_until_ms), "PX", ttl_ms)
return {count, blocked_until_ms, penalty_sec}
"""


@dataclass(frozen=True)
class RateLimitDecision:
    """Evaluated rate-limit state returned from Redis or fail-open bypass."""

    allowed: bool
    limit: int
    remaining: int
    retry_after: int


@dataclass(frozen=True)
class LoginPolicy:
    """Resolved login failure tolerances and progressive backoff tiers."""

    pair_free_attempts: int
    pair_steps: list[int]
    ip_free_attempts: int
    ip_steps: list[int]
    dist_email_limit: int
    dist_steps: list[int]
    window_ms: int


def _now_ms() -> int:
    """Current epoch timestamp in milliseconds."""
    return int(time.time() * 1000)


@lru_cache(maxsize=16)
def _parse_networks(
    cidrs: tuple[str, ...],
) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    """Parse CIDR strings into ip_network objects, caching per CIDR tuple."""
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for cidr in cidrs:
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            logger.warning("rate_limit.invalid_trusted_cidr", cidr=cidr)
    return tuple(networks)


def _is_trusted_ip(
    raw_ip: str,
    trusted_networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...],
) -> bool:
    """Return True if raw_ip parses as an address inside trusted_networks."""
    try:
        addr = ipaddress.ip_address(raw_ip.strip())
    except ValueError:
        return False
    return any(addr in net for net in trusted_networks)


def extract_client_ip(request: Request, settings: Settings) -> str:
    """Resolve client IP while only trusting X-Forwarded-For from configured proxy hops."""
    peer_ip = request.client.host if request.client else "unknown"
    trusted_networks = _parse_networks(tuple(settings.TRUSTED_PROXY_CIDRS))

    if peer_ip != "unknown" and _is_trusted_ip(peer_ip, trusted_networks):
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            candidates = [part.strip() for part in forwarded_for.split(",") if part.strip()]
            # Walk right-to-left to pick the first hop outside trusted proxies
            for candidate in reversed(candidates):
                if not _is_trusted_ip(candidate, trusted_networks):
                    return candidate
            if candidates:
                return candidates[0]
    return peer_ip


async def _extract_normalized_email(request: Request) -> str | None:
    """Safely inspect cached JSON body for an email field without breaking route parsing."""
    raw_body = await request.body()
    if not raw_body:
        return None
    try:
        payload = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError):
        return None
    if isinstance(payload, dict):
        email = payload.get("email")
        if isinstance(email, str) and email.strip():
            return email.strip().lower()
    return None


def _raise_rate_limited(max_requests: int, retry_after: int) -> NoReturn:
    """Raise standardized HTTP 429 with Retry-After and X-RateLimit-* headers."""
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many requests. Please try again later.",
        headers={
            "Retry-After": str(max(retry_after, 1)),
            "X-RateLimit-Limit": str(max(max_requests, 1)),
            "X-RateLimit-Remaining": "0",
        },
    )


def apply_rate_limit_headers(response: Response | None, decision: RateLimitDecision) -> None:
    """Attach X-RateLimit-* headers to outbound responses."""
    if response is None:
        return
    response.headers["X-RateLimit-Limit"] = str(decision.limit)
    response.headers["X-RateLimit-Remaining"] = str(max(decision.remaining, 0))


def resolve_bucket_params(
    base_limit: int,
    window_seconds: int,
    settings: Settings,
) -> tuple[int, int]:
    """Adjust capacity/window according to effective rate-limit profile."""
    safe_limit = max(base_limit, 1)
    safe_window = max(window_seconds, 1)
    if settings.effective_rate_limit_profile == "relaxed_dev":
        return max(safe_limit, settings.RATE_LIMIT_DEV_BURST), min(safe_window, 60)
    return safe_limit, safe_window


async def enforce_rate_limit(
    *,
    redis_client: aioredis.Redis,
    settings: Settings,
    key: str,
    max_requests: int,
    window_seconds: int,
    scope: str,
) -> RateLimitDecision:
    """Check and consume a single Token Bucket from Redis."""
    capacity = max(max_requests, 1)
    safe_window = max(window_seconds, 1)
    refill_per_sec = capacity / float(safe_window)
    now_ms = _now_ms()
    ttl_ms = max(safe_window * 1000, 60_000)

    try:
        eval_fn: Any = redis_client.eval
        result = await eval_fn(
            _TOKEN_BUCKET_LUA,
            1,
            key,
            str(capacity),
            f"{refill_per_sec:.9f}",
            str(now_ms),
            str(ttl_ms),
        )
    except Exception:
        logger.exception("rate_limit.redis_error", scope=scope)
        if settings.RATE_LIMIT_FAIL_CLOSED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rate limiter temporarily unavailable",
            ) from None
        return RateLimitDecision(allowed=True, limit=capacity, remaining=capacity, retry_after=0)

    allowed = bool(int(result[0]))
    remaining = max(int(result[1]), 0)
    retry_after = max(int(result[2]), 0)

    if not allowed:
        logger.warning("auth.rate_limited", scope=scope, retry_after=retry_after)
        _raise_rate_limited(capacity, retry_after)

    return RateLimitDecision(allowed=True, limit=capacity, remaining=remaining, retry_after=0)


def resolve_login_policy(settings: Settings) -> LoginPolicy:
    """Resolve active login failure limits and progressive backoff tiers."""
    window_ms = max(settings.AUTH_LOGIN_FAILURE_WINDOW_SECONDS, 60) * 1000
    if settings.effective_rate_limit_profile == "relaxed_dev":
        short_step = [max(settings.RATE_LIMIT_DEV_BACKOFF_SECONDS, 1)]
        return LoginPolicy(
            pair_free_attempts=max(settings.AUTH_RATE_LIMIT_LOGIN_EMAIL, 1),
            pair_steps=short_step,
            ip_free_attempts=max(settings.AUTH_RATE_LIMIT_LOGIN_IP, settings.RATE_LIMIT_DEV_BURST),
            ip_steps=short_step,
            dist_email_limit=max(
                settings.AUTH_LOGIN_DISTRIBUTED_EMAIL_LIMIT,
                settings.RATE_LIMIT_DEV_BURST,
            ),
            dist_steps=short_step,
            window_ms=window_ms,
        )

    steps = list(settings.AUTH_LOGIN_BACKOFF_STEPS) or [5, 15, 60, 300]
    return LoginPolicy(
        pair_free_attempts=max(settings.AUTH_RATE_LIMIT_LOGIN_EMAIL, 1),
        pair_steps=steps,
        ip_free_attempts=max(settings.AUTH_RATE_LIMIT_LOGIN_IP, 1),
        ip_steps=steps,
        dist_email_limit=max(settings.AUTH_LOGIN_DISTRIBUTED_EMAIL_LIMIT, 1),
        dist_steps=[60, 300],
        window_ms=window_ms,
    )


def _login_fail_keys(client_ip: str, normalized_email: str) -> tuple[str, str, str]:
    """Return Redis keys for composite (ip, email), ip spray, and distributed email failure tracking."""
    pair_key = f"auth:rl:login:fail:pair:{hash_token(f'{client_ip}:{normalized_email}')}"
    ip_key = f"auth:rl:login:fail:ip:{hash_token(client_ip)}"
    dist_email_key = f"auth:rl:login:fail:dist_email:{hash_token(normalized_email)}"
    return pair_key, ip_key, dist_email_key


async def check_login_cooldown(
    *,
    redis_client: aioredis.Redis,
    settings: Settings,
    client_ip: str,
    email: str,
) -> None:
    """Reject active login cooldowns BEFORE Argon2id password verification runs."""
    if not settings.RATE_LIMIT_ENABLED:
        return

    normalized_email = email.strip().lower()
    pair_key, ip_key, dist_email_key = _login_fail_keys(client_ip, normalized_email)
    policy = resolve_login_policy(settings)
    now_ms = _now_ms()

    try:
        eval_fn: Any = redis_client.eval
        result = await eval_fn(
            _FAILURE_CHECK_LUA,
            3,
            pair_key,
            ip_key,
            dist_email_key,
            str(now_ms),
        )
    except Exception:
        logger.exception("rate_limit.login_check_redis_error")
        if settings.RATE_LIMIT_FAIL_CLOSED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rate limiter temporarily unavailable",
            ) from None
        return

    retry_after = int(result[0])
    blocking_idx = int(result[1])
    if retry_after > 0:
        limits = (policy.pair_free_attempts, policy.ip_free_attempts, policy.dist_email_limit)
        limit_val = limits[blocking_idx - 1] if 1 <= blocking_idx <= len(limits) else limits[0]
        scope_names = ("login:pair", "login:ip", "login:distributed_email")
        scope_name = (
            scope_names[blocking_idx - 1] if 1 <= blocking_idx <= len(scope_names) else "login"
        )
        logger.warning("auth.rate_limited", scope=scope_name, retry_after=retry_after)
        _raise_rate_limited(limit_val, retry_after)


async def record_login_failure(
    *,
    redis_client: aioredis.Redis,
    settings: Settings,
    client_ip: str,
    email: str,
) -> None:
    """Increment failure counters and arm progressive backoff after tolerated attempts."""
    if not settings.RATE_LIMIT_ENABLED:
        return

    normalized_email = email.strip().lower()
    pair_key, ip_key, dist_email_key = _login_fail_keys(client_ip, normalized_email)
    policy = resolve_login_policy(settings)
    now_ms = _now_ms()

    buckets = (
        ("login:pair", pair_key, policy.pair_free_attempts, policy.pair_steps),
        ("login:ip", ip_key, policy.ip_free_attempts, policy.ip_steps),
        ("login:distributed_email", dist_email_key, policy.dist_email_limit, policy.dist_steps),
    )

    try:
        eval_fn: Any = redis_client.eval
        for scope_name, key, free_attempts, steps in buckets:
            res = await eval_fn(
                _FAILURE_RECORD_LUA,
                1,
                key,
                str(free_attempts),
                str(policy.window_ms),
                str(now_ms),
                *[str(step) for step in steps],
            )
            penalty = int(res[2])
            if penalty > 0:
                logger.warning(
                    "auth.login_backoff_armed",
                    scope=scope_name,
                    failure_count=int(res[0]),
                    cooldown_seconds=penalty,
                )
    except Exception:
        logger.exception("rate_limit.login_record_redis_error")
        if settings.RATE_LIMIT_FAIL_CLOSED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rate limiter temporarily unavailable",
            ) from None


async def clear_login_failures(
    *,
    redis_client: aioredis.Redis,
    settings: Settings,
    client_ip: str,
    email: str,
) -> None:
    """Reset the composite (ip, email) failure streak after a valid login."""
    if not settings.RATE_LIMIT_ENABLED:
        return

    normalized_email = email.strip().lower()
    pair_key, _, _ = _login_fail_keys(client_ip, normalized_email)
    try:
        await redis_client.delete(pair_key)
    except Exception:
        logger.exception("rate_limit.login_clear_redis_error")


def rate_limit(
    scope: str,
    max_requests: int | Callable[[Settings], int],
    window_seconds: int,
    *,
    email_max_requests: int | Callable[[Settings], int] | None = None,
    email_window_seconds: int | None = None,
) -> Callable[[Request, Response, aioredis.Redis, Settings], Awaitable[None]]:
    """Build a FastAPI dependency enforcing Token Bucket IP (and composite email) limits."""

    async def _dependency(
        request: Request,
        response: Response,
        redis_client: aioredis.Redis = Depends(get_redis),
        settings: Settings = Depends(get_settings),
    ) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return

        client_ip = extract_client_ip(request, settings)
        base_ip_limit = max_requests(settings) if callable(max_requests) else max_requests

        # When scoped with an email field (e.g. /forgot, /resend-verification), evaluate
        # composite (ip, email) + distributed email cap first so one bad actor does not burn
        # a shared NAT IP budget; grant NAT IPs a wider aggregate ceiling.
        if email_max_requests is not None and email_window_seconds is not None:
            raw_email_limit = (
                email_max_requests(settings) if callable(email_max_requests) else email_max_requests
            )
            email = await _extract_normalized_email(request)
            pair_cap, pair_win = resolve_bucket_params(
                raw_email_limit, email_window_seconds, settings
            )
            if email:
                pair_key = f"auth:rl:{scope}:pair:{hash_token(f'{client_ip}:{email}')}"
                pair_decision = await enforce_rate_limit(
                    redis_client=redis_client,
                    settings=settings,
                    key=pair_key,
                    max_requests=pair_cap,
                    window_seconds=pair_win,
                    scope=f"{scope}:pair",
                )
                dist_cap, dist_win = resolve_bucket_params(
                    max(raw_email_limit * 5, 15), email_window_seconds, settings
                )
                dist_key = f"auth:rl:{scope}:dist_email:{hash_token(email)}"
                await enforce_rate_limit(
                    redis_client=redis_client,
                    settings=settings,
                    key=dist_key,
                    max_requests=dist_cap,
                    window_seconds=dist_win,
                    scope=f"{scope}:distributed_email",
                )
                apply_rate_limit_headers(response, pair_decision)

            nat_cap, nat_win = resolve_bucket_params(
                max(base_ip_limit * 4, 12), window_seconds, settings
            )
            ip_key = f"auth:rl:{scope}:ip:{hash_token(client_ip)}"
            ip_decision = await enforce_rate_limit(
                redis_client=redis_client,
                settings=settings,
                key=ip_key,
                max_requests=nat_cap,
                window_seconds=nat_win,
                scope=f"{scope}:ip",
            )
            if not email:
                apply_rate_limit_headers(response, ip_decision)
            return

        ip_cap, ip_win = resolve_bucket_params(base_ip_limit, window_seconds, settings)
        ip_key = f"auth:rl:{scope}:ip:{hash_token(client_ip)}"
        decision = await enforce_rate_limit(
            redis_client=redis_client,
            settings=settings,
            key=ip_key,
            max_requests=ip_cap,
            window_seconds=ip_win,
            scope=f"{scope}:ip",
        )
        apply_rate_limit_headers(response, decision)

    return _dependency


async def enforce_actor_rate_limit(
    *,
    response: Response | None,
    redis_client: aioredis.Redis,
    settings: Settings,
    scope: str,
    actor_key: str,
    max_requests: int,
    window_seconds: int,
) -> None:
    """Enforce Token Bucket keyed by verified user/organization actor instead of shared IP."""
    if not settings.RATE_LIMIT_ENABLED:
        return

    cap, win = resolve_bucket_params(max_requests, window_seconds, settings)
    decision = await enforce_rate_limit(
        redis_client=redis_client,
        settings=settings,
        key=f"auth:rl:{scope}:actor:{hash_token(actor_key)}",
        max_requests=cap,
        window_seconds=win,
        scope=f"{scope}:actor",
    )
    apply_rate_limit_headers(response, decision)
