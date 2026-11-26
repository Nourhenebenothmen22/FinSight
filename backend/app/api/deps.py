"""Shared FastAPI dependencies for authentication, CSRF checks, and client metadata."""

import uuid
from typing import Annotated
from urllib.parse import urlparse

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import get_db
from app.core.rate_limit import extract_client_ip
from app.core.security import get_current_user_id
from app.models.auth import User


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
