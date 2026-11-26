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


def _prod_base_kwargs(test_settings: Settings) -> dict[str, object]:
    """Build valid baseline production settings overrides for validator unit tests."""
    dumped = test_settings.model_dump(
        exclude={
            "DATABASE_URL",
            "REDIS_URL",
            "QDRANT_URL",
            "S3_ENDPOINT",
            "S3_ENDPOINT_URL",
            "S3_ADMIN_URL",
            "OLLAMA_URL",
        }
    )
    dumped.update(
        {
            "APP_ENV": "production",
            "FRONTEND_URL": "https://app.finsight.example",
            "SECRET_KEY": "a" * 40,
            "POSTGRES_PASSWORD": "strong_password_123",
            "S3_ACCESS_KEY": "GK000000000000000000000000",
            "S3_SECRET_KEY": "0" * 64,
            "ADMIN_PASSWORD": "real-admin-password",
            "TRUSTED_PROXY_CIDRS": ["127.0.0.0/8", "10.0.1.0/24"],
        }
    )
    return dumped


def test_production_rejects_placeholder_secrets(test_settings: Settings) -> None:
    """Production configuration rejects weak/placeholder SECRET_KEY."""
    kwargs = _prod_base_kwargs(test_settings)
    kwargs["SECRET_KEY"] = "CHANGE_ME_IN_PRODUCTION"
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(**kwargs)  # type: ignore[arg-type]


def test_rate_limit_profile_and_trusted_proxy_validators(test_settings: Settings) -> None:
    """Dev uses relaxed_dev profile while staging/prod force strict limits and narrow proxy CIDRs."""
    dev_kwargs = _prod_base_kwargs(test_settings)
    dev_kwargs["APP_ENV"] = "development"
    dev_kwargs["FRONTEND_URL"] = "http://localhost:3000"
    dev_settings = Settings(**dev_kwargs)  # type: ignore[arg-type]
    assert dev_settings.effective_rate_limit_profile == "relaxed_dev"
    assert dev_settings.RATE_LIMIT_ENABLED is True

    strict_prod = Settings(**_prod_base_kwargs(test_settings))  # type: ignore[arg-type]
    assert strict_prod.effective_rate_limit_profile == "strict"

    relaxed_prod = _prod_base_kwargs(test_settings)
    relaxed_prod["RATE_LIMIT_PROFILE"] = "relaxed_dev"
    with pytest.raises(ValueError, match="RATE_LIMIT_PROFILE"):
        Settings(**relaxed_prod)  # type: ignore[arg-type]

    disabled_staging = _prod_base_kwargs(test_settings)
    disabled_staging["APP_ENV"] = "staging"
    disabled_staging["RATE_LIMIT_ENABLED"] = False
    with pytest.raises(ValueError, match="RATE_LIMIT_ENABLED"):
        Settings(**disabled_staging)  # type: ignore[arg-type]

    for broad_cidr in ("0.0.0.0/0", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"):
        bad_proxy = _prod_base_kwargs(test_settings)
        bad_proxy["TRUSTED_PROXY_CIDRS"] = [broad_cidr]
        with pytest.raises(ValueError, match="TRUSTED_PROXY_CIDRS"):
            Settings(**bad_proxy)  # type: ignore[arg-type]
