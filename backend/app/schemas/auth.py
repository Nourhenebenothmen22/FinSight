"""Authentication Pydantic request and response schemas (F1)."""

import re
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, model_validator

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128
MAX_NAME_LENGTH = 120

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def _normalize_email(value: EmailStr) -> str:
    """Normalize email addresses consistently to trimmed lowercase."""
    return str(value).strip().lower()


def _normalize_name(value: str) -> str:
    """Trim whitespace and reject empty or control-character-laden names."""
    cleaned = _CONTROL_CHARS_RE.sub("", value).strip()
    if not cleaned:
        raise ValueError("Name must not be empty")
    return cleaned


def validate_password_strength(password: str) -> str:
    """Enforce baseline password length and character-class complexity."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters long")
    if not any(ch.islower() for ch in password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not any(ch.isupper() for ch in password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not any(ch.isdigit() for ch in password):
        raise ValueError("Password must contain at least one digit")
    if not any(not ch.isalnum() for ch in password):
        raise ValueError("Password must contain at least one special character")
    return password


NormalizedEmail = Annotated[EmailStr, AfterValidator(_normalize_email)]
CleanName = Annotated[
    str, Field(min_length=1, max_length=MAX_NAME_LENGTH), AfterValidator(_normalize_name)
]
StrongPassword = Annotated[
    str,
    Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH),
    AfterValidator(validate_password_strength),
]


class RegisterRequest(BaseModel):
    """User registration request payload."""

    name: CleanName
    email: NormalizedEmail
    password: StrongPassword


class LoginRequest(BaseModel):
    """Email and password login request payload."""

    email: NormalizedEmail
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class RefreshRequest(BaseModel):
    """Optional JSON payload for clients not using HttpOnly refresh cookies."""

    refresh_token: str | None = Field(default=None, min_length=16, max_length=2048)


class LogoutRequest(BaseModel):
    """Optional JSON payload for revoking a refresh token passed outside cookies."""

    refresh_token: str | None = Field(default=None, min_length=16, max_length=2048)


class VerifyEmailRequest(BaseModel):
    """Single-use email verification payload."""

    token: str = Field(min_length=16, max_length=512)


class ResendVerificationRequest(BaseModel):
    """Request to resend an email verification link."""

    email: NormalizedEmail


class ForgotPasswordRequest(BaseModel):
    """Request to initiate a password reset email."""

    email: NormalizedEmail


class ResetPasswordRequest(BaseModel):
    """Complete password reset using a single-use token."""

    token: str = Field(min_length=16, max_length=512)
    new_password: StrongPassword


class UpdateProfileRequest(BaseModel):
    """Update authenticated user profile attributes."""

    name: CleanName


class ChangePasswordRequest(BaseModel):
    """Change or set the authenticated user's password."""

    current_password: str | None = Field(default=None, max_length=MAX_PASSWORD_LENGTH)
    new_password: StrongPassword

    @model_validator(mode="after")
    def validate_distinct_passwords(self) -> "ChangePasswordRequest":
        """Reject replacing the password with the exact same password."""
        if self.current_password and self.current_password == self.new_password:
            raise ValueError("New password must differ from the current password")
        return self


class GoogleExchangeRequest(BaseModel):
    """Exchange a single-use OAuth callback code for an access token."""

    code: str = Field(min_length=16, max_length=512)


class UserResponse(BaseModel):
    """Public representation of an authenticated FinSight user."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    email_verified_at: datetime | None
    oauth_provider: str | None
    has_password: bool
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class RegisterResponse(BaseModel):
    """Response returned after successful registration."""

    message: str
    user: UserResponse


class TokenResponse(BaseModel):
    """Authentication token response returned upon login, refresh, or OAuth exchange."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str | None = None
    user: UserResponse
    next_path: str | None = None


class SessionResponse(BaseModel):
    """Active refresh-token session visible on the user's profile."""

    id: uuid.UUID
    user_agent: str | None
    ip_address: str | None
    created_at: datetime
    expires_at: datetime
    is_current: bool


class MessageResponse(BaseModel):
    """Generic status message response."""

    message: str
