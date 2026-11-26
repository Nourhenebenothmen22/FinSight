"""Shared FastAPI dependencies for authentication, tenant context, RBAC, and CSRF checks."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlparse

import redis.asyncio as aioredis
import structlog
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import bind_tenant_rls, get_db
from app.core.rate_limit import enforce_actor_rate_limit, extract_client_ip
from app.core.redis import get_redis
from app.core.security import get_current_user_id
from app.models.auth import User
from app.models.tenant import Membership, Organization, OrgRole


async def get_current_user(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Load the active authenticated user from PostgreSQL."""
    try:
        parsed_id = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    result = await db.execute(select(User).where(User.id == parsed_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )
    return user


def _extract_origin(url_value: str) -> str | None:
    """Return normalized scheme://netloc for an origin/URL string."""
    parsed = urlparse(url_value.strip())
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
    return None


def verify_cookie_csrf_origin(request: Request, settings: Settings) -> None:
    """Validate Origin/Referer on cookie-authenticated mutations to mitigate CSRF."""
    allowed_origins = {
        origin
        for value in [settings.FRONTEND_URL, *settings.CORS_ORIGINS]
        if (origin := _extract_origin(value)) is not None
    }
    origin_header = request.headers.get("origin")
    if origin_header:
        normalized = _extract_origin(origin_header)
        if normalized is None or normalized not in allowed_origins:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cross-site request rejected",
            )
        return

    referer_header = request.headers.get("referer")
    if referer_header:
        normalized_ref = _extract_origin(referer_header)
        if normalized_ref is None or normalized_ref not in allowed_origins:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cross-site request rejected",
            )


def extract_client_metadata(request: Request, settings: Settings) -> tuple[str | None, str | None]:
    """Return sanitized (user_agent, client_ip) for refresh session recording."""
    raw_ua = request.headers.get("user-agent")
    user_agent = raw_ua.replace("\r", "").replace("\n", "").strip()[:255] if raw_ua else None
    client_ip = extract_client_ip(request, settings)
    ip_value = None if client_ip == "unknown" else client_ip[:64]
    return user_agent or None, ip_value


@dataclass(frozen=True)
class TenantContext:
    """Verified server-side tenant context for the current request."""

    tenant_id: uuid.UUID
    organization: Organization
    membership: Membership
    role: OrgRole
    user: User


def _parse_optional_tenant_header(request: Request) -> uuid.UUID | None:
    """Parse X-Tenant-ID header safely if provided by the client."""
    raw_header = request.headers.get("x-tenant-id", "").strip()
    if not raw_header:
        return None
    try:
        return uuid.UUID(raw_header)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid X-Tenant-ID header",
        ) from None


async def get_tenant_context(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    org_id: uuid.UUID | None = None,
) -> TenantContext:
    """Resolve and authorize the active tenant from path org_id, X-Tenant-ID, or default org."""
    header_org_id = _parse_optional_tenant_header(request)
    target_org_id = org_id or header_org_id

    if target_org_id is not None:
        stmt = (
            select(Membership, Organization)
            .join(Organization, Organization.id == Membership.org_id)
            .where(
                Membership.org_id == target_org_id,
                Membership.user_id == current_user.id,
                Membership.accepted_at.is_not(None),
            )
            .limit(1)
        )
    else:
        stmt = (
            select(Membership, Organization)
            .join(Organization, Organization.id == Membership.org_id)
            .where(
                Membership.user_id == current_user.id,
                Membership.accepted_at.is_not(None),
            )
            .order_by(Membership.created_at.asc())
            .limit(1)
        )

    row = (await db.execute(stmt)).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied for this organization",
        )

    membership, organization = row
    request.state.tenant_id = str(organization.id)
    structlog.contextvars.bind_contextvars(tenant_id=str(organization.id))

    return TenantContext(
        tenant_id=organization.id,
        organization=organization,
        membership=membership,
        role=OrgRole(membership.role),
        user=current_user,
    )


async def get_tenant_db(
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncSession:
    """Return an AsyncSession bound to transaction-local PostgreSQL RLS for tenant_id."""
    await bind_tenant_rls(db, tenant.tenant_id, rls_role=settings.POSTGRES_RLS_ROLE)
    return db


def require_org_roles(
    *allowed_roles: OrgRole,
) -> Callable[[TenantContext], Awaitable[TenantContext]]:
    """FastAPI dependency enforcing server-side organization RBAC permissions."""
    allowed = frozenset(allowed_roles)

    async def _dependency(
        tenant: Annotated[TenantContext, Depends(get_tenant_context)],
    ) -> TenantContext:
        if tenant.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient organization permissions",
            )
        return tenant

    return _dependency


def user_rate_limit(
    scope: str,
    max_requests: int | Callable[[Settings], int],
    window_seconds: int,
) -> Callable[[Response, User, aioredis.Redis, Settings], Awaitable[None]]:
    """Build a FastAPI dependency applying Token Bucket limits keyed by verified user_id."""

    async def _dependency(
        response: Response,
        current_user: Annotated[User, Depends(get_current_user)],
        redis_client: Annotated[aioredis.Redis, Depends(get_redis)],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> None:
        limit = max_requests(settings) if callable(max_requests) else max_requests
        await enforce_actor_rate_limit(
            response=response,
            redis_client=redis_client,
            settings=settings,
            scope=scope,
            actor_key=f"user:{current_user.id}",
            max_requests=limit,
            window_seconds=window_seconds,
        )

    return _dependency


def org_rate_limit(
    scope: str,
    max_requests: int | Callable[[Settings], int],
    window_seconds: int,
    *,
    allowed_roles: tuple[OrgRole, ...] = (),
) -> Callable[[Response, TenantContext, aioredis.Redis, Settings], Awaitable[None]]:
    """Enforce RBAC role checks first, then apply Token Bucket keyed by (org_id, user_id)."""
    allowed = frozenset(allowed_roles)

    async def _dependency(
        response: Response,
        tenant: Annotated[TenantContext, Depends(get_tenant_context)],
        redis_client: Annotated[aioredis.Redis, Depends(get_redis)],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> None:
        if allowed and tenant.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient organization permissions",
            )
        limit = max_requests(settings) if callable(max_requests) else max_requests
        await enforce_actor_rate_limit(
            response=response,
            redis_client=redis_client,
            settings=settings,
            scope=scope,
            actor_key=f"org:{tenant.tenant_id}:user:{tenant.user.id}",
            max_requests=limit,
            window_seconds=window_seconds,
        )

    return _dependency
