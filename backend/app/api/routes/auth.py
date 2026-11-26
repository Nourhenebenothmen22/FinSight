"""Authentication REST endpoints (F1)."""

import uuid
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    extract_client_metadata,
    get_current_user,
    user_rate_limit,
    verify_cookie_csrf_origin,
)
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.queue import TaskDispatcher, get_task_dispatcher
from app.core.rate_limit import rate_limit
from app.core.redis import get_redis
from app.models.auth import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    GoogleExchangeRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SessionResponse,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
    VerifyEmailRequest,
)
from app.services import auth as auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_OAUTH_STATE_COOKIE_NAME = "finsight_oauth_state"
_OAUTH_STATE_COOKIE_PATH = "/api/v1/auth/google"
_SECONDS_PER_DAY = 86400
_ONE_MINUTE = 60
_FIVE_MINUTES = 300
_FIFTEEN_MINUTES = 900


def _set_refresh_cookie(response: Response, refresh_token: str, settings: Settings) -> None:
    """Attach an HttpOnly refresh token cookie scoped to /api."""
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * _SECONDS_PER_DAY,
        path=settings.AUTH_COOKIE_PATH,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    """Delete the HttpOnly refresh token cookie."""
    response.delete_cookie(
        key=settings.AUTH_COOKIE_NAME,
        path=settings.AUTH_COOKIE_PATH,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )


def _to_token_response(
    session: auth_service.IssuedSession,
    *,
    include_refresh_token: bool = True,
    next_path: str | None = None,
) -> TokenResponse:
    """Convert IssuedSession to TokenResponse."""
    return TokenResponse(
        access_token=session.access_token,
        expires_in=session.expires_in,
        refresh_token=session.refresh_token if include_refresh_token else None,
        user=session.user,
        next_path=next_path,
    )


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    dependencies=[
        Depends(
            rate_limit(
                "register",
                max_requests=lambda s: s.AUTH_RATE_LIMIT_REGISTER,
                window_seconds=_FIFTEEN_MINUTES,
            )
        )
    ],
)
async def register(
    payload: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
) -> RegisterResponse:
    """Register with name, email, and password (Argon2id) and dispatch verification email."""
    user = await auth_service.register_user(db, payload, settings, dispatcher)
    return RegisterResponse(
        message="Account created. Please check your email to verify your address.",
        user=user,
    )


@router.post(
    "/verify",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify user email address",
    dependencies=[
        Depends(
            rate_limit(
                "verify",
                max_requests=lambda s: s.AUTH_RATE_LIMIT_VERIFY,
                window_seconds=_FIFTEEN_MINUTES,
            )
        )
    ],
)
async def verify_email(
    payload: VerifyEmailRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    """Confirm user email ownership using a single-use verification token."""
    await auth_service.verify_email_token(db, payload.token)
    return MessageResponse(message="Email verified successfully. You can now sign in.")


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Resend email verification link",
    dependencies=[
        Depends(
            rate_limit(
                "resend_verify",
                max_requests=lambda s: s.AUTH_RATE_LIMIT_FORGOT,
                window_seconds=_FIFTEEN_MINUTES,
                email_max_requests=lambda s: s.AUTH_RATE_LIMIT_FORGOT,
                email_window_seconds=_FIFTEEN_MINUTES,
            )
        )
    ],
)
async def resend_verification(
    payload: ResendVerificationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
) -> MessageResponse:
    """Resend email verification link without leaking whether the email is registered."""
    await auth_service.resend_verification_email(db, payload.email, settings, dispatcher)
    return MessageResponse(
        message="If an unverified account exists for this email, a verification link has been sent."
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate with email and password",
)
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    *,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[aioredis.Redis, Depends(get_redis)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    """Sign in with email/password using failure-only progressive backoff and JWT rotation."""
    user_agent, ip_address = extract_client_metadata(request, settings)
    session = await auth_service.login_user(
        db,
        payload,
        settings,
        user_agent=user_agent,
        ip_address=ip_address,
        redis_client=redis_client,
    )
    _set_refresh_cookie(response, session.refresh_token, settings)
    return _to_token_response(session)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate refresh token and issue a new access token",
    dependencies=[
        Depends(
            rate_limit(
                "refresh",
                max_requests=lambda s: s.AUTH_RATE_LIMIT_REFRESH,
                window_seconds=_FIVE_MINUTES,
            )
        )
    ],
)
async def refresh(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    payload: Annotated[RefreshRequest | None, Body()] = None,
) -> TokenResponse:
    """Rotate a refresh token provided via HttpOnly cookie or JSON body."""
    body_token = payload.refresh_token if payload else None
    cookie_token = request.cookies.get(settings.AUTH_COOKIE_NAME)
    if body_token is None and cookie_token is not None:
        verify_cookie_csrf_origin(request, settings)

    raw_token = body_token or cookie_token
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_agent, ip_address = extract_client_metadata(request, settings)
    session = await auth_service.refresh_session(
        db,
        raw_token,
        settings,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    _set_refresh_cookie(response, session.refresh_token, settings)
    return _to_token_response(session)


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke current refresh session and clear auth cookie",
)
async def logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    payload: Annotated[LogoutRequest | None, Body()] = None,
) -> MessageResponse:
    """Sign out of the current session."""
    body_token = payload.refresh_token if payload else None
    cookie_token = request.cookies.get(settings.AUTH_COOKIE_NAME)
    if body_token is None and cookie_token is not None:
        verify_cookie_csrf_origin(request, settings)

    await auth_service.logout_session(db, body_token or cookie_token)
    _clear_refresh_cookie(response, settings)
    return MessageResponse(message="Logged out successfully.")


@router.post(
    "/logout-all",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke all active refresh sessions for the authenticated user",
)
async def logout_all(
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    """Sign out from every active device/session."""
    await auth_service.logout_all_sessions(db, current_user)
    _clear_refresh_cookie(response, settings)
    return MessageResponse(message="All active sessions have been revoked.")


@router.post(
    "/forgot",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Initiate password reset email",
    dependencies=[
        Depends(
            rate_limit(
                "forgot",
                max_requests=lambda s: s.AUTH_RATE_LIMIT_FORGOT,
                window_seconds=_FIFTEEN_MINUTES,
                email_max_requests=lambda s: s.AUTH_RATE_LIMIT_FORGOT,
                email_window_seconds=_FIFTEEN_MINUTES,
            )
        )
    ],
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
) -> MessageResponse:
    """Request a password reset email without disclosing account existence."""
    await auth_service.request_password_reset(db, payload.email, settings, dispatcher)
    return MessageResponse(
        message="If an account exists for this email, a password reset link has been sent."
    )


@router.post(
    "/reset",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Complete password reset",
    dependencies=[
        Depends(
            rate_limit(
                "reset",
                max_requests=lambda s: s.AUTH_RATE_LIMIT_RESET,
                window_seconds=_FIFTEEN_MINUTES,
            )
        )
    ],
)
async def reset_password(
    response: Response,
    payload: ResetPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    """Reset user password with a single-use token and revoke active sessions."""
    await auth_service.reset_password(db, payload.token, payload.new_password)
    _clear_refresh_cookie(response, settings)
    return MessageResponse(message="Password updated successfully. Please sign in again.")


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get authenticated user profile",
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Return the authenticated user's profile."""
    return auth_service.to_user_response(current_user)


@router.patch(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update authenticated user profile",
)
async def update_me(
    payload: UpdateProfileRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Update profile attributes for the authenticated user."""
    return await auth_service.update_user_profile(db, current_user, payload)


@router.post(
    "/change-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Change or set user password",
    dependencies=[
        Depends(
            user_rate_limit(
                "change_password",
                max_requests=lambda s: s.AUTH_RATE_LIMIT_RESET,
                window_seconds=_FIFTEEN_MINUTES,
            )
        )
    ],
)
async def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    """Update authenticated user's password and revoke other active sessions."""
    cookie_token = request.cookies.get(settings.AUTH_COOKIE_NAME)
    await auth_service.change_user_password(
        db,
        current_user,
        payload,
        current_refresh_token=cookie_token,
    )
    return MessageResponse(message="Password updated successfully.")


@router.get(
    "/sessions",
    response_model=list[SessionResponse],
    status_code=status.HTTP_200_OK,
    summary="List active refresh sessions",
)
async def list_sessions(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[SessionResponse]:
    """Return active refresh sessions for the authenticated user."""
    cookie_token = request.cookies.get(settings.AUTH_COOKIE_NAME)
    return await auth_service.list_user_sessions(db, current_user, cookie_token)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a specific active session",
)
async def delete_session(
    session_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Revoke one active refresh session owned by the authenticated user."""
    await auth_service.revoke_user_session_by_id(db, current_user, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/google/login",
    status_code=status.HTTP_302_FOUND,
    summary="Redirect to Google OAuth authorization endpoint",
    dependencies=[
        Depends(
            rate_limit(
                "google_login",
                max_requests=lambda s: s.AUTH_RATE_LIMIT_REFRESH,
                window_seconds=_FIVE_MINUTES,
            )
        )
    ],
)
async def google_login(
    redis_client: Annotated[aioredis.Redis, Depends(get_redis)],
    settings: Annotated[Settings, Depends(get_settings)],
    next_path: Annotated[str | None, Query(alias="next")] = None,
) -> RedirectResponse:
    """Start Google OAuth Authorization Code + PKCE flow."""
    authorize_url, state_cookie_hash = await auth_service.build_google_authorize_redirect(
        redis_client,
        settings,
        next_path=next_path,
    )
    redirect_response = RedirectResponse(url=authorize_url, status_code=status.HTTP_302_FOUND)
    redirect_response.set_cookie(
        key=_OAUTH_STATE_COOKIE_NAME,
        value=state_cookie_hash,
        max_age=600,
        path=_OAUTH_STATE_COOKIE_PATH,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )
    return redirect_response


@router.get(
    "/google/callback",
    status_code=status.HTTP_302_FOUND,
    summary="Handle Google OAuth callback",
    dependencies=[
        Depends(
            rate_limit(
                "google_callback",
                max_requests=lambda s: s.AUTH_RATE_LIMIT_REFRESH,
                window_seconds=_FIVE_MINUTES,
            )
        )
    ],
)
async def google_callback(
    request: Request,
    *,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[aioredis.Redis, Depends(get_redis)],
    settings: Annotated[Settings, Depends(get_settings)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Validate Google callback and redirect to frontend with single-use exchange code."""
    state_cookie_hash = request.cookies.get(_OAUTH_STATE_COOKIE_NAME)
    redirect_url = await auth_service.complete_google_callback(
        db,
        redis_client,
        settings,
        code=code,
        state=state,
        state_cookie_hash=state_cookie_hash,
        error_param=error,
    )
    redirect_response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    redirect_response.delete_cookie(
        key=_OAUTH_STATE_COOKIE_NAME,
        path=_OAUTH_STATE_COOKIE_PATH,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )
    return redirect_response


@router.post(
    "/google/exchange",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange single-use OAuth code for FinSight tokens",
    dependencies=[
        Depends(
            rate_limit(
                "google_exchange",
                max_requests=lambda s: s.AUTH_RATE_LIMIT_VERIFY,
                window_seconds=_FIFTEEN_MINUTES,
            )
        )
    ],
)
async def google_exchange(
    request: Request,
    response: Response,
    payload: GoogleExchangeRequest,
    *,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[aioredis.Redis, Depends(get_redis)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    """Complete Google OAuth sign-in by issuing refresh cookie and access token."""
    user_agent, ip_address = extract_client_metadata(request, settings)
    session, next_path = await auth_service.exchange_oauth_ephemeral_code(
        db,
        redis_client,
        settings,
        payload.code,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    _set_refresh_cookie(response, session.refresh_token, settings)
    return _to_token_response(session, next_path=next_path)
