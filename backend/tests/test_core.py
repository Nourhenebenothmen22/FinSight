"""Unit tests for core configuration, security, and database base consistency."""

from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.core.database import Base as DatabaseBase
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.models.base import Base as ModelsBase


def test_single_sqlalchemy_base() -> None:
    """Ensure database.py and models/base.py share the exact same Base class."""
    assert DatabaseBase is ModelsBase


def test_password_hashing_and_verification() -> None:
    """Argon2id hashes verify correctly and reject wrong passwords."""
    hashed = get_password_hash("CorrectHorseBatteryStaple!2026")
    assert hashed.startswith("$argon2id$")
    assert verify_password("CorrectHorseBatteryStaple!2026", hashed) is True
    assert verify_password("wrong-password", hashed) is False
    assert verify_password("anything", "not-a-valid-hash") is False


def test_jwt_access_and_refresh_tokens() -> None:
    """JWT access and refresh tokens encode and decode claims properly."""
    access = create_access_token("user-123", extra_claims={"org_id": "org-456"})
    payload = decode_token(access)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"
    assert payload["org_id"] == "org-456"

    refresh = create_refresh_token("user-123")
    refresh_payload = decode_token(refresh)
    assert refresh_payload["sub"] == "user-123"
    assert refresh_payload["type"] == "refresh"


def test_expired_jwt_is_rejected() -> None:
    """Expired JWT tokens raise HTTP 401."""
    expired = create_access_token("user-123", expires_delta=timedelta(seconds=-10))
    with pytest.raises(HTTPException) as exc_info:
        decode_token(expired)
    assert exc_info.value.status_code == 401


def test_production_rejects_placeholder_secrets(test_settings: Settings) -> None:
    """Production configuration rejects weak/placeholder SECRET_KEY."""
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(
            **{
                **test_settings.model_dump(
                    exclude={
                        "DATABASE_URL",
                        "REDIS_URL",
                        "QDRANT_URL",
                        "S3_ENDPOINT",
                        "S3_ENDPOINT_URL",
                        "S3_ADMIN_URL",
                        "OLLAMA_URL",
                    }
                ),
                "APP_ENV": "production",
                "SECRET_KEY": "CHANGE_ME_IN_PRODUCTION",
                "POSTGRES_PASSWORD": "strong_password",
                "S3_ACCESS_KEY": "GK000000000000000000000000",
                "S3_SECRET_KEY": "0" * 64,
                "ADMIN_PASSWORD": "real-admin-password",
            }
        )
