"""Security utilities: password hashing (Argon2id), JWT tokens."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import get_settings


def _get_password_hasher() -> PasswordHasher:
    """Build Argon2id PasswordHasher from application settings."""
    settings = get_settings()
    return PasswordHasher(
        time_cost=settings.ARGON2_TIME_COST,
        memory_cost=settings.ARGON2_MEMORY_COST,
        parallelism=settings.ARGON2_PARALLELISM,
        hash_len=32,
        salt_len=16,
        type=Type.ID,
    )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its Argon2id hash."""
    try:
        return _get_password_hasher().verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def get_password_hash(password: str) -> str:
    """Hash a password using Argon2id."""
    return _get_password_hasher().hash(password)


# -----------------------------------------------------------------------------
# JWT Tokens
# -----------------------------------------------------------------------------
def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a JWT access token."""
    settings = get_settings()
    to_encode: dict[str, Any] = {"sub": str(subject), "type": "access"}
    if extra_claims:
        to_encode.update(extra_claims)

    expire = datetime.now(UTC) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire

    encoded: str = jwt.encode(
        to_encode,
        settings.SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded


def create_refresh_token(
    subject: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT refresh token."""
    settings = get_settings()
    expire = datetime.now(UTC) + (
        expires_delta
        if expires_delta is not None
        else timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    to_encode: dict[str, Any] = {
        "sub": str(subject),
        "type": "refresh",
        "exp": expire,
    }

    encoded: str = jwt.encode(
        to_encode,
        settings.SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token."""
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.SECRET_KEY.get_secret_value(),
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    else:
        return payload


# -----------------------------------------------------------------------------
# FastAPI Dependencies
# -----------------------------------------------------------------------------
security = HTTPBearer(auto_error=False)

TokenData = Annotated[HTTPAuthorizationCredentials | None, Depends(security)]


async def get_current_user_id(token: TokenData) -> str:
    """Extract user ID from JWT access token."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token.credentials)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_id


async def get_current_user_id_optional(token: TokenData) -> str | None:
    """Extract user ID from JWT access token (optional - returns None if invalid)."""
    if not token:
        return None

    try:
        payload = decode_token(token.credentials)
        if payload.get("type") != "access":
            return None
        user_id = payload.get("sub")
        return user_id if isinstance(user_id, str) and user_id else None
    except HTTPException:
        return None
