"""Redis-backed rate limiting with atomic window expiry and trusted-proxy IP resolution."""

import ipaddress
import json
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as aioredis
import structlog
from fastapi import Depends, HTTPException, Request, status

from app.core.config import Settings, get_settings
from app.core.redis import get_redis
from app.core.security import hash_token

logger = structlog.get_logger(__name__)

_RATE_LIMIT_LUA = """
local current = redis.call("INCR", KEYS[1])
if current == 1 then
  redis.call("EXPIRE", KEYS[1], ARGV[1])
end
local ttl = redis.call("TTL", KEYS[1])
if ttl < 0 then
  redis.call("EXPIRE", KEYS[1], ARGV[1])
  ttl = tonumber(ARGV[1])
end
return {current, ttl}
"""


def _parse_networks(
    cidrs: list[str],
) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Parse CIDR strings into ip_network objects, ignoring invalid entries safely."""
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for cidr in cidrs:
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            logger.warning("rate_limit.invalid_trusted_cidr", cidr=cidr)
    return networks


def _is_trusted_ip(
    raw_ip: str,
    trusted_networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network],
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
    trusted_networks = _parse_networks(settings.TRUSTED_PROXY_CIDRS)

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


async def _increment_window(
    redis_client: aioredis.Redis,
    key: str,
    window_seconds: int,
) -> tuple[int, int]:
    """Atomically increment counter and return (count, ttl_seconds)."""
    eval_fn: Any = redis_client.eval
    result = await eval_fn(_RATE_LIMIT_LUA, 1, key, str(window_seconds))
    count = int(result[0])
    ttl = max(int(result[1]), 1)
    return count, ttl


async def enforce_rate_limit(
    *,
    redis_client: aioredis.Redis,
    settings: Settings,
    key: str,
    max_requests: int,
    window_seconds: int,
    scope: str,
) -> None:
    """Check and enforce a single rate-limit bucket."""
    try:
        count, ttl = await _increment_window(redis_client, key, window_seconds)
    except Exception:
        logger.exception("rate_limit.redis_error", scope=scope)
        if settings.RATE_LIMIT_FAIL_CLOSED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rate limiter temporarily unavailable",
            ) from None
        return

    if count > max_requests:
        logger.warning("auth.rate_limited", scope=scope, retry_after=ttl)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
            headers={
                "Retry-After": str(ttl),
                "X-RateLimit-Limit": str(max_requests),
                "X-RateLimit-Remaining": "0",
            },
        )


def rate_limit(
    scope: str,
    max_requests: int | Callable[[Settings], int],
    window_seconds: int,
    *,
    email_max_requests: int | Callable[[Settings], int] | None = None,
    email_window_seconds: int | None = None,
) -> Callable[[Request, aioredis.Redis, Settings], Awaitable[None]]:
    """Build a FastAPI dependency enforcing IP (and optionally email-hash) rate limits."""

    async def _dependency(
        request: Request,
        redis_client: aioredis.Redis = Depends(get_redis),
        settings: Settings = Depends(get_settings),
    ) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return

        ip_limit = max_requests(settings) if callable(max_requests) else max_requests
        client_ip = extract_client_ip(request, settings)
        ip_key = f"auth:rl:{scope}:ip:{hash_token(client_ip)}"
        await enforce_rate_limit(
            redis_client=redis_client,
            settings=settings,
            key=ip_key,
            max_requests=ip_limit,
            window_seconds=window_seconds,
            scope=f"{scope}:ip",
        )

        if email_max_requests is not None and email_window_seconds is not None:
            email_limit = (
                email_max_requests(settings) if callable(email_max_requests) else email_max_requests
            )
            email = await _extract_normalized_email(request)
            if email:
                email_key = f"auth:rl:{scope}:email:{hash_token(email)}"
                await enforce_rate_limit(
                    redis_client=redis_client,
                    settings=settings,
                    key=email_key,
                    max_requests=email_limit,
                    window_seconds=email_window_seconds,
                    scope=f"{scope}:email",
                )

    return _dependency
