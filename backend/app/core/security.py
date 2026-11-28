"""Security utilities: password hashing (Argon2id), JWT tokens, opaque tokens, OIDC validation."""

import base64
import hashlib
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated, Any

import httpx
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import get_settings

_GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_GOOGLE_ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})
_JWKS_CACHE_TTL_SECONDS = 3600


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


@lru_cache
def _get_dummy_password_hash() -> str:
    """Compute a dummy Argon2id hash once per process for constant-time auth checks."""
    return get_password_hash("FinSight-Constant-Time-Dummy-Password-Guard!")


def verify_password_constant_time(plain_password: str, hashed_password: str | None) -> bool:
    """Verify a password while keeping work uniform even if hash is absent."""
    if not hashed_password:
        verify_password(plain_password, _get_dummy_password_hash())
        return False
    return verify_password(plain_password, hashed_password)


# -----------------------------------------------------------------------------
# Opaque & PKCE Tokens
# -----------------------------------------------------------------------------
def generate_opaque_token() -> str:
    """Generate a high-entropy URL-safe opaque token."""
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest of a raw token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_pkce_pair() -> tuple[str, str]:
    """Generate an RFC 7636 PKCE (code_verifier, S256 code_challenge) pair."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


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
    now = datetime.now(UTC)
    to_encode: dict[str, Any] = {
        "sub": str(subject),
        "type": "access",
        "jti": uuid.uuid4().hex,
        "iat": now,
    }
    if extra_claims:
        to_encode.update(extra_claims)

    expire = now + (
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
    """Create a JWT refresh token with a unique jti."""
    settings = get_settings()
    now = datetime.now(UTC)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    to_encode: dict[str, Any] = {
        "sub": str(subject),
        "type": "refresh",
        "jti": uuid.uuid4().hex,
        "iat": now,
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
# Google OIDC ID Token Validation
# -----------------------------------------------------------------------------
@dataclass
class _JwksCache:
    keys: list[dict[str, Any]] = field(default_factory=list)
    fetched_at: float = 0.0


_google_jwks_cache = _JwksCache()


async def fetch_google_jwks(timeout_seconds: float = 10.0) -> list[dict[str, Any]]:
    """Fetch Google's public JWKS keys."""
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.get(_GOOGLE_JWKS_URL)
        response.raise_for_status()
        data = response.json()
    keys = data.get("keys")
    if not isinstance(keys, list):
        raise TypeError("Invalid JWKS response from Google")
    return [key for key in keys if isinstance(key, dict)]


async def _get_google_signing_key(
    kid: str | None,
    timeout_seconds: float,
) -> dict[str, Any] | None:
    """Resolve Google JWK by key ID with TTL caching and miss refresh."""
    now = time.monotonic()
    stale = (now - _google_jwks_cache.fetched_at) > _JWKS_CACHE_TTL_SECONDS
    if stale or not _google_jwks_cache.keys:
        _google_jwks_cache.keys = await fetch_google_jwks(timeout_seconds=timeout_seconds)
        _google_jwks_cache.fetched_at = now

    for key in _google_jwks_cache.keys:
        if key.get("kid") == kid:
            return key

    # Key rotated upstream: refresh once
    _google_jwks_cache.keys = await fetch_google_jwks(timeout_seconds=timeout_seconds)
    _google_jwks_cache.fetched_at = time.monotonic()
    for key in _google_jwks_cache.keys:
        if key.get("kid") == kid:
            return key
    return None


async def verify_google_id_token(
    id_token: str,
    client_id: str,
    timeout_seconds: float = 10.0,
    access_token: str | None = None,
) -> dict[str, Any]:
    """Cryptographically verify a Google OIDC ID token and its claims."""
    try:
        header = jwt.get_unverified_header(id_token)
        kid = header.get("kid")
        key = await _get_google_signing_key(
            kid=kid if isinstance(kid, str) else None,
            timeout_seconds=timeout_seconds,
        )
    except (JWTError, httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google identity token",
        ) from exc

    if key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to verify Google identity token",
        )

    try:
        payload: dict[str, Any] = jwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            audience=client_id,
            access_token=access_token,
            options={"require_aud": True, "require_exp": True, "require_sub": True},
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google identity token",
        ) from exc

    issuer = payload.get("iss")
    email = payload.get("email")
    subject = payload.get("sub")
    if (
        issuer not in _GOOGLE_ISSUERS
        or payload.get("email_verified") is not True
        or not isinstance(email, str)
        or not email.strip()
        or not isinstance(subject, str)
        or not subject.strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google account email is not verified or claims are incomplete",
        )

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
