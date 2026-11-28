"""Authentication service implementing registration, login, rotation, reset, and Google OAuth."""

import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import urlencode, urlparse

import httpx
import redis.asyncio as aioredis
import structlog
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.queue import TaskDispatcher
from app.core.rate_limit import check_login_cooldown, clear_login_failures, record_login_failure
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_opaque_token,
    generate_pkce_pair,
    get_password_hash,
    hash_token,
    verify_google_id_token,
    verify_password,
    verify_password_constant_time,
)
from app.models.auth import AuthToken, RefreshToken, User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    SessionResponse,
    UpdateProfileRequest,
    UserResponse,
)
from app.services.email import build_action_url
from app.services.tenant import create_personal_organization_for_user

logger = structlog.get_logger(__name__)

_TOKEN_PURPOSE_VERIFY = "email_verification"
_TOKEN_PURPOSE_RESET = "password_reset"
_OAUTH_STATE_TTL_SECONDS = 600
_OAUTH_EXCHANGE_TTL_SECONDS = 60
_ASCII_CONTROL_UPPER = 32
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

_REDIS_GETDEL_LUA = """
local val = redis.call("GET", KEYS[1])
if val then
  redis.call("DEL", KEYS[1])
end
return val
"""


@dataclass(frozen=True)
class IssuedSession:
    """Tokens and user data issued after authentication or refresh."""

    access_token: str
    refresh_token: str
    expires_in: int
    user: UserResponse


def ensure_utc(dt: datetime) -> datetime:
    """Normalize naive datetimes (e.g. from SQLite tests) to UTC-aware datetimes."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def sanitize_next_path(next_path: str | None, default: str = "/profile") -> str:
    """Allow only safe same-origin relative redirect paths to prevent open redirects."""
    if not next_path:
        return default
    candidate = next_path.strip()
    if (
        not candidate.startswith("/")
        or candidate.startswith("//")
        or "\\" in candidate
        or any(ord(ch) < _ASCII_CONTROL_UPPER for ch in candidate)
    ):
        return default
    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc:
        return default
    return candidate


def to_user_response(user: User) -> UserResponse:
    """Convert a User ORM instance to a public UserResponse schema."""
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        email_verified_at=user.email_verified_at,
        oauth_provider=user.oauth_provider,
        has_password=user.password_hash is not None,
        is_active=user.is_active,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


async def _invalidate_unused_auth_tokens(
    db: AsyncSession,
    user_id: uuid.UUID,
    purpose: str,
    now: datetime,
) -> None:
    """Mark any previously unused action tokens for this user and purpose as consumed."""
    await db.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user_id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        )
        .values(used_at=now)
    )


async def _create_auth_token(
    db: AsyncSession,
    user_id: uuid.UUID,
    purpose: str,
    expires_delta: timedelta,
) -> str:
    """Invalidate older unused tokens for the purpose and persist a fresh hashed token."""
    now = datetime.now(UTC)
    await _invalidate_unused_auth_tokens(db, user_id, purpose, now)

    raw_token = generate_opaque_token()
    token_row = AuthToken(
        user_id=user_id,
        purpose=purpose,
        token_hash=hash_token(raw_token),
        expires_at=now + expires_delta,
    )
    db.add(token_row)
    await db.flush()
    return raw_token


async def _revoke_all_user_refresh_tokens(
    db: AsyncSession,
    user_id: uuid.UUID,
    reason: str,
    *,
    exclude_token_id: uuid.UUID | None = None,
) -> None:
    """Revoke all active refresh tokens belonging to user_id."""
    now = datetime.now(UTC)
    stmt = (
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now, revocation_reason=reason)
    )
    if exclude_token_id is not None:
        stmt = stmt.where(RefreshToken.id != exclude_token_id)
    await db.execute(stmt)


async def _issue_session_tokens(
    db: AsyncSession,
    user: User,
    settings: Settings,
    *,
    family_id: uuid.UUID | None = None,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[IssuedSession, uuid.UUID]:
    """Create and persist a new refresh token row and return paired access + refresh JWTs."""
    now = datetime.now(UTC)
    resolved_family = family_id or uuid.uuid4()
    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    refresh_expires = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    refresh_row = RefreshToken(
        user_id=user.id,
        family_id=resolved_family,
        token_hash=hash_token(refresh_token),
        expires_at=refresh_expires,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    db.add(refresh_row)
    await db.flush()

    session = IssuedSession(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=to_user_response(user),
    )
    return session, refresh_row.id


async def _enqueue_email_task(
    dispatcher: TaskDispatcher,
    task_name: str,
    to_email: str,
    user_name: str,
    action_url: str,
) -> None:
    """Enqueue an email job onto ARQ, translating transport failures into HTTP 503."""
    try:
        await dispatcher.enqueue(task_name, to_email, user_name, action_url)
    except Exception as exc:
        logger.exception("auth.email_enqueue_failed", task_name=task_name)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email notification service is temporarily unavailable",
        ) from exc


async def register_user(
    db: AsyncSession,
    payload: RegisterRequest,
    settings: Settings,
    dispatcher: TaskDispatcher,
) -> UserResponse:
    """Create a new unverified user account and enqueue verification email."""
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        name=payload.name,
        email_verified_at=None,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from None

    await create_personal_organization_for_user(db, user)

    raw_token = await _create_auth_token(
        db=db,
        user_id=user.id,
        purpose=_TOKEN_PURPOSE_VERIFY,
        expires_delta=timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS),
    )
    verification_url = build_action_url(settings.EMAIL_VERIFICATION_BASE_URL, raw_token)
    await _enqueue_email_task(
        dispatcher,
        "send_verification_email_task",
        user.email,
        user.name,
        verification_url,
    )
    await db.commit()
    await db.refresh(user)
    logger.info("auth.register", user_id=str(user.id))
    return to_user_response(user)


def _affected_one(result: Any) -> bool:
    """Check that an UPDATE affected exactly one database row."""
    cursor = cast(CursorResult[Any], result)
    return cursor.rowcount == 1


async def _consume_auth_token(
    db: AsyncSession,
    raw_token: str,
    purpose: str,
    invalid_detail: str,
) -> tuple[User, datetime]:
    """Atomically verify and consume a single-use AuthToken, returning (User, now)."""
    now = datetime.now(UTC)
    token_hash = hash_token(raw_token)
    result = await db.execute(
        select(AuthToken).where(
            AuthToken.token_hash == token_hash,
            AuthToken.purpose == purpose,
        )
    )
    token_row = result.scalar_one_or_none()

    if (
        token_row is None
        or token_row.used_at is not None
        or ensure_utc(token_row.expires_at) <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=invalid_detail,
        )

    consumed = await db.execute(
        update(AuthToken)
        .where(AuthToken.id == token_row.id, AuthToken.used_at.is_(None))
        .values(used_at=now)
    )
    if not _affected_one(consumed):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=invalid_detail,
        )

    user_result = await db.execute(select(User).where(User.id == token_row.user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=invalid_detail,
        )

    return user, now


async def verify_email_token(db: AsyncSession, raw_token: str) -> None:
    """Consume a single-use email verification token and activate email verification."""
    user, now = await _consume_auth_token(
        db,
        raw_token,
        _TOKEN_PURPOSE_VERIFY,
        "Verification token is invalid or expired",
    )
    if user.email_verified_at is None:
        user.email_verified_at = now
    await db.commit()
    logger.info("auth.email_verified", user_id=str(user.id))


async def resend_verification_email(
    db: AsyncSession,
    email: str,
    settings: Settings,
    dispatcher: TaskDispatcher,
) -> None:
    """Re-issue a verification email for unverified accounts without leaking existence."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or user.email_verified_at is not None:
        return

    raw_token = await _create_auth_token(
        db=db,
        user_id=user.id,
        purpose=_TOKEN_PURPOSE_VERIFY,
        expires_delta=timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS),
    )
    verification_url = build_action_url(settings.EMAIL_VERIFICATION_BASE_URL, raw_token)
    await _enqueue_email_task(
        dispatcher,
        "send_verification_email_task",
        user.email,
        user.name,
        verification_url,
    )
    await db.commit()
    logger.info("auth.verification_resent", user_id=str(user.id))


async def login_user(
    db: AsyncSession,
    payload: LoginRequest,
    settings: Settings,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
    redis_client: aioredis.Redis | None = None,
) -> IssuedSession:
    """Authenticate an email/password user with cooldown check before Argon2id."""
    rate_ip = ip_address or "unknown"
    if redis_client is not None:
        await check_login_cooldown(
            redis_client=redis_client,
            settings=settings,
            client_ip=rate_ip,
            email=payload.email,
        )

    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    password_valid = verify_password_constant_time(
        payload.password,
        user.password_hash if user is not None else None,
    )
    if user is None or not password_valid:
        if redis_client is not None:
            await record_login_failure(
                redis_client=redis_client,
                settings=settings,
                client_ip=rate_ip,
                email=payload.email,
            )
        logger.warning("auth.login_failed", email_hash=hash_token(payload.email))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    if user.email_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email address is not verified",
        )

    user.last_login_at = datetime.now(UTC)
    session, _ = await _issue_session_tokens(
        db,
        user,
        settings,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    await db.commit()
    if redis_client is not None:
        await clear_login_failures(
            redis_client=redis_client,
            settings=settings,
            client_ip=rate_ip,
            email=payload.email,
        )
    logger.info("auth.login_success", user_id=str(user.id))
    return session


async def refresh_session(
    db: AsyncSession,
    raw_refresh_token: str,
    settings: Settings,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> IssuedSession:
    """Rotate a refresh token, detecting reuse across the entire token family."""
    payload = decode_token(raw_refresh_token)
    if payload.get("type") != "refresh" or not isinstance(payload.get("jti"), str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    now = datetime.now(UTC)
    token_hash = hash_token(raw_refresh_token)
    row_result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    token_row = row_result.scalar_one_or_none()

    if token_row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token_row.revoked_at is not None:
        # Compromised/reused refresh token: revoke the entire family durably before raising
        await db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == token_row.family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now, revocation_reason="reuse_detected")
        )
        await db.commit()
        logger.warning(
            "auth.refresh_reuse_detected",
            user_id=str(token_row.user_id),
            family_id=str(token_row.family_id),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected; session family revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if ensure_utc(token_row.expires_at) <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_result = await db.execute(select(User).where(User.id == token_row.user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account unavailable",
            headers={"WWW-Authenticate": "Bearer"},
        )

    consumed = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.id == token_row.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now, revocation_reason="rotated")
    )
    if not _affected_one(consumed):
        await db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == token_row.family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now, revocation_reason="reuse_detected")
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token already used",
            headers={"WWW-Authenticate": "Bearer"},
        )

    new_session, new_token_id = await _issue_session_tokens(
        db,
        user,
        settings,
        family_id=token_row.family_id,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.id == token_row.id)
        .values(replaced_by_id=new_token_id)
    )
    await db.commit()
    logger.info("auth.refresh_rotated", user_id=str(user.id))
    return new_session


async def logout_session(db: AsyncSession, raw_refresh_token: str | None) -> None:
    """Revoke a single refresh token if supplied and still active."""
    if not raw_refresh_token:
        return
    token_hash = hash_token(raw_refresh_token)
    now = datetime.now(UTC)
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now, revocation_reason="logout")
    )
    await db.commit()


async def logout_all_sessions(db: AsyncSession, user: User) -> None:
    """Revoke every active refresh session owned by user."""
    await _revoke_all_user_refresh_tokens(db, user.id, "logout_all")
    await db.commit()
    logger.info("auth.logout_all", user_id=str(user.id))


async def request_password_reset(
    db: AsyncSession,
    email: str,
    settings: Settings,
    dispatcher: TaskDispatcher,
) -> None:
    """Create a password reset token and enqueue email without disclosing existence."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return

    raw_token = await _create_auth_token(
        db=db,
        user_id=user.id,
        purpose=_TOKEN_PURPOSE_RESET,
        expires_delta=timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES),
    )
    reset_url = build_action_url(settings.PASSWORD_RESET_BASE_URL, raw_token)
    await _enqueue_email_task(
        dispatcher,
        "send_password_reset_email_task",
        user.email,
        user.name,
        reset_url,
    )
    await db.commit()
    logger.info("auth.password_reset_requested", user_id=str(user.id))


async def reset_password(db: AsyncSession, raw_token: str, new_password: str) -> None:
    """Validate single-use reset token, update password, and revoke active sessions."""
    user, now = await _consume_auth_token(
        db,
        raw_token,
        _TOKEN_PURPOSE_RESET,
        "Password reset token is invalid or expired",
    )
    user.password_hash = get_password_hash(new_password)
    if user.email_verified_at is None:
        user.email_verified_at = now
    await _revoke_all_user_refresh_tokens(db, user.id, "password_reset")
    await db.commit()
    logger.info("auth.password_reset_completed", user_id=str(user.id))


async def update_user_profile(
    db: AsyncSession,
    user: User,
    payload: UpdateProfileRequest,
) -> UserResponse:
    """Update mutable profile attributes for the authenticated user."""
    user.name = payload.name
    await db.commit()
    await db.refresh(user)
    return to_user_response(user)


async def change_user_password(
    db: AsyncSession,
    user: User,
    payload: ChangePasswordRequest,
    *,
    current_refresh_token: str | None = None,
) -> None:
    """Change (or initially set for OAuth accounts) the user's password and revoke other sessions."""
    if user.password_hash is not None:
        if not payload.current_password or not verify_password(
            payload.current_password, user.password_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

    exclude_token_id: uuid.UUID | None = None
    if current_refresh_token:
        current_row_result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_token(current_refresh_token),
                RefreshToken.user_id == user.id,
                RefreshToken.revoked_at.is_(None),
            )
        )
        current_row = current_row_result.scalar_one_or_none()
        if current_row is not None:
            exclude_token_id = current_row.id

    user.password_hash = get_password_hash(payload.new_password)
    await _revoke_all_user_refresh_tokens(
        db,
        user.id,
        "password_changed",
        exclude_token_id=exclude_token_id,
    )
    await db.commit()
    logger.info("auth.password_changed", user_id=str(user.id))


async def list_user_sessions(
    db: AsyncSession,
    user: User,
    current_refresh_token: str | None,
) -> list[SessionResponse]:
    """Return active (non-revoked, unexpired) refresh sessions for user."""
    now = datetime.now(UTC)
    current_hash = hash_token(current_refresh_token) if current_refresh_token else None

    result = await db.execute(
        select(RefreshToken)
        .where(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        .order_by(RefreshToken.created_at.desc())
    )
    rows = result.scalars().all()
    return [
        SessionResponse(
            id=row.id,
            user_agent=row.user_agent,
            ip_address=row.ip_address,
            created_at=row.created_at,
            expires_at=row.expires_at,
            is_current=current_hash is not None
            and secrets.compare_digest(row.token_hash, current_hash),
        )
        for row in rows
    ]


async def revoke_user_session_by_id(
    db: AsyncSession,
    user: User,
    session_id: uuid.UUID,
) -> None:
    """Revoke a specific refresh session owned by the authenticated user."""
    now = datetime.now(UTC)
    result = await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.id == session_id,
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now, revocation_reason="user_revoked")
    )
    if not _affected_one(result):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active session not found",
        )
    await db.commit()


# -----------------------------------------------------------------------------
# Google OAuth 2.0 / OIDC Flow
# -----------------------------------------------------------------------------
async def _redis_getdel(redis_client: aioredis.Redis, key: str) -> str | None:
    """Atomically read and delete a Redis key."""
    eval_fn = redis_client.eval
    result = await eval_fn(_REDIS_GETDEL_LUA, 1, key)  # type: ignore[misc]
    return result if isinstance(result, str) else None


async def build_google_authorize_redirect(
    redis_client: aioredis.Redis,
    settings: Settings,
    next_path: str | None = None,
) -> tuple[str, str]:
    """Create PKCE+state OAuth authorization URL and hashed state cookie value."""
    if not settings.google_oauth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured",
        )

    state = generate_opaque_token()
    code_verifier, code_challenge = generate_pkce_pair()
    safe_next = sanitize_next_path(next_path, default="/profile")

    state_payload = json.dumps({"code_verifier": code_verifier, "next_path": safe_next})
    await redis_client.set(
        f"auth:oauth:state:{state}",
        state_payload,
        ex=_OAUTH_STATE_TTL_SECONDS,
    )

    params = urlencode(
        {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "select_account",
        }
    )
    return f"{_GOOGLE_AUTH_URL}?{params}", hash_token(state)


async def exchange_google_authorization_code(
    *,
    code: str,
    code_verifier: str,
    settings: Settings,
) -> dict[str, object]:
    """Exchange Google authorization code and PKCE verifier at Google token endpoint."""
    async with httpx.AsyncClient(timeout=float(settings.GOOGLE_OAUTH_TIMEOUT_SECONDS)) as client:
        response = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET.get_secret_value(),
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
        )
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise TypeError("Unexpected response from Google token endpoint")
    return data


async def _validate_and_consume_oauth_state(
    redis_client: aioredis.Redis,
    *,
    code: str | None,
    state: str | None,
    state_cookie_hash: str | None,
) -> tuple[str, str] | None:
    """Validate OAuth CSRF state cookie + Redis entry, returning (code_verifier, next_path)."""
    if (
        not code
        or not state
        or not state_cookie_hash
        or not secrets.compare_digest(hash_token(state), state_cookie_hash)
    ):
        return None
    raw_state = await _redis_getdel(redis_client, f"auth:oauth:state:{state}")
    if not raw_state:
        return None
    state_data = json.loads(raw_state)
    code_verifier = str(state_data["code_verifier"])
    next_path = sanitize_next_path(state_data.get("next_path"), default="/profile")
    return code_verifier, next_path


async def _resolve_google_user(
    db: AsyncSession,
    claims: dict[str, object],
    now: datetime,
) -> tuple[User | None, str | None]:
    """Find or create a verified user for Google claims, returning (user, error_code)."""
    sub = str(claims["sub"]).strip()
    email = str(claims["email"]).strip().lower()
    raw_name = claims.get("name")
    display_name = (
        str(raw_name).strip()[:120]
        if isinstance(raw_name, str) and raw_name.strip()
        else email.split("@", maxsplit=1)[0][:120]
    )

    result = await db.execute(
        select(User).where(User.oauth_provider == "google", User.oauth_subject == sub)
    )
    user = result.scalar_one_or_none()
    if user is None:
        email_result = await db.execute(select(User).where(User.email == email))
        existing_user = email_result.scalar_one_or_none()
        if existing_user is not None:
            # Block pre-hijacking: never auto-link to an unverified password account
            if existing_user.email_verified_at is None:
                logger.warning("auth.oauth_unverified_conflict", user_id=str(existing_user.id))
                return None, "email_unverified_conflict"
            if (
                existing_user.oauth_provider == "google"
                and existing_user.oauth_subject is not None
                and existing_user.oauth_subject != sub
            ):
                return None, "oauth_subject_mismatch"
            existing_user.oauth_provider = "google"
            existing_user.oauth_subject = sub
            user = existing_user
        else:
            user = User(
                email=email,
                password_hash=None,
                name=display_name,
                email_verified_at=now,
                oauth_provider="google",
                oauth_subject=sub,
            )
            db.add(user)
            await db.flush()
            await create_personal_organization_for_user(db, user)

    if not user.is_active:
        return None, "account_inactive"
    return user, None


async def complete_google_callback(
    db: AsyncSession,
    redis_client: aioredis.Redis,
    settings: Settings,
    *,
    code: str | None,
    state: str | None,
    state_cookie_hash: str | None,
    error_param: str | None,
) -> str:
    """Handle Google OAuth callback and return safe frontend redirect URL."""
    frontend_base = settings.FRONTEND_URL.rstrip("/")
    oauth_error: str | None = None

    if not settings.google_oauth_enabled:
        oauth_error = "oauth_unavailable"
    elif error_param:
        oauth_error = "oauth_denied"

    state_pair = None
    if oauth_error is None:
        state_pair = await _validate_and_consume_oauth_state(
            redis_client,
            code=code,
            state=state,
            state_cookie_hash=state_cookie_hash,
        )
        if state_pair is None:
            oauth_error = "invalid_state"

    if oauth_error is not None or state_pair is None or code is None:
        return f"{frontend_base}/login?oauth_error={oauth_error or 'invalid_state'}"

    code_verifier, next_path = state_pair
    try:
        token_data = await exchange_google_authorization_code(
            code=code,
            code_verifier=code_verifier,
            settings=settings,
        )
        id_token = token_data.get("id_token")
        if not isinstance(id_token, str) or not id_token:
            return f"{frontend_base}/login?oauth_error=oauth_failed"
        raw_access_token = token_data.get("access_token")
        google_access_token = (
            raw_access_token if isinstance(raw_access_token, str) and raw_access_token else None
        )
        claims = await verify_google_id_token(
            id_token=id_token,
            client_id=settings.GOOGLE_CLIENT_ID,
            timeout_seconds=float(settings.GOOGLE_OAUTH_TIMEOUT_SECONDS),
            access_token=google_access_token,
        )
    except (httpx.HTTPError, ValueError, HTTPException):
        logger.exception("auth.google_token_exchange_failed")
        return f"{frontend_base}/login?oauth_error=oauth_failed"

    now = datetime.now(UTC)
    user, conflict_error = await _resolve_google_user(db, claims, now)
    if conflict_error is not None or user is None:
        return f"{frontend_base}/login?oauth_error={conflict_error or 'oauth_failed'}"

    user.last_login_at = now
    await db.commit()

    exchange_code = generate_opaque_token()
    exchange_payload = json.dumps({"user_id": str(user.id), "next_path": next_path})
    await redis_client.set(
        f"auth:oauth:exchange:{hash_token(exchange_code)}",
        exchange_payload,
        ex=_OAUTH_EXCHANGE_TTL_SECONDS,
    )
    logger.info("auth.oauth_google_login", user_id=str(user.id))

    callback_query = urlencode({"code": exchange_code})
    return f"{frontend_base}/auth/google/callback?{callback_query}"


async def exchange_oauth_ephemeral_code(
    db: AsyncSession,
    redis_client: aioredis.Redis,
    settings: Settings,
    code: str,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[IssuedSession, str]:
    """Exchange a single-use OAuth code for full FinSight session tokens and next_path."""
    raw_payload = await _redis_getdel(redis_client, f"auth:oauth:exchange:{hash_token(code)}")
    if not raw_payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OAuth exchange code is invalid or expired",
        )

    payload = json.loads(raw_payload)
    try:
        user_id = uuid.UUID(str(payload["user_id"]))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid OAuth exchange payload",
        ) from None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account unavailable",
        )

    session, _ = await _issue_session_tokens(
        db,
        user,
        settings,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    await db.commit()
    next_path = sanitize_next_path(payload.get("next_path"), default="/profile")
    return session, next_path
