"""Application configuration using Pydantic Settings.

All settings are loaded from environment variables with validation at startup.
Required variables will raise ValidationError if missing.
"""

import ipaddress
import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BeforeValidator,
    Field,
    PostgresDsn,
    RedisDsn,
    SecretStr,
    computed_field,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"
MIN_SECRET_KEY_LENGTH = 32


def parse_cors(v: Any) -> list[str]:
    """Parse CORS origins from string or list."""
    if isinstance(v, list):
        return [str(item).strip() for item in v if str(item).strip()]
    if isinstance(v, str):
        stripped = v.strip()
        if not stripped:
            return []
        return [item.strip() for item in stripped.split(",") if item.strip()]
    raise ValueError(f"Invalid CORS_ORIGINS value: {type(v).__name__}")


def parse_int_list(v: Any) -> list[int]:
    """Parse positive integer sequences from list, JSON array, or comma-separated string."""
    if isinstance(v, list):
        values = [int(item) for item in v]
    elif isinstance(v, str):
        stripped = v.strip()
        if not stripped:
            raise ValueError("Backoff step list cannot be empty")
        if stripped.startswith("[") and stripped.endswith("]"):
            parsed = json.loads(stripped)
            if not isinstance(parsed, list):
                raise ValueError("Invalid JSON list for integer sequence")
            values = [int(item) for item in parsed]
        else:
            values = [int(item.strip()) for item in stripped.split(",") if item.strip()]
    else:
        raise TypeError(f"Invalid integer list value: {type(v).__name__}")
    if not values or any(val <= 0 for val in values):
        raise ValueError("All backoff steps must be positive integers")
    return values


_IPV4_VERSION = 4
_IPV6_VERSION = 6
_MIN_PROD_PROXY_IPV4_PREFIX = 20
_MIN_PROD_PROXY_IPV6_PREFIX = 48
_BROAD_PRIVATE_PROXY_NETS = frozenset(
    {
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
    }
)


class Settings(BaseSettings):
    """Application settings with environment variable loading."""

    model_config = SettingsConfigDict(
        env_file=(str(_ROOT_ENV), ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        validate_default=True,
    )

    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------
    APP_ENV: str = Field(
        default="development",
        pattern="^(development|test|staging|production)$",
    )
    APP_NAME: str = "FinSight"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:3000"
    BACKEND_INTERNAL_URL: str = "http://api:8000"

    CORS_ORIGINS: Annotated[list[str], BeforeValidator(parse_cors)] = Field(
        default=["http://localhost:3000"]
    )

    # -------------------------------------------------------------------------
    # Security
    # -------------------------------------------------------------------------
    SECRET_KEY: SecretStr = Field(
        default=...,
        description="Secret key for JWT signing. Generate with: openssl rand -hex 32",
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    ARGON2_TIME_COST: int = 3
    ARGON2_MEMORY_COST: int = 65536
    ARGON2_PARALLELISM: int = 4

    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30
    ORG_INVITATION_EXPIRE_DAYS: int = 7

    AUTH_COOKIE_NAME: str = "finsight_refresh_token"
    AUTH_COOKIE_PATH: str = "/api"
    AUTH_COOKIE_SECURE: bool | None = None
    AUTH_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"

    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_FAIL_CLOSED: bool = False
    RATE_LIMIT_PROFILE: Literal["auto", "relaxed_dev", "strict"] = "auto"
    RATE_LIMIT_DEV_BURST: int = Field(default=20, ge=1)
    RATE_LIMIT_DEV_BACKOFF_SECONDS: int = Field(default=5, ge=1)
    TRUSTED_PROXY_CIDRS: Annotated[list[str], BeforeValidator(parse_cors)] = Field(
        default=["127.0.0.0/8", "::1/128", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
    )
    AUTH_RATE_LIMIT_LOGIN_IP: int = 10
    AUTH_RATE_LIMIT_LOGIN_EMAIL: int = 5
    AUTH_LOGIN_BACKOFF_STEPS: Annotated[list[int], BeforeValidator(parse_int_list)] = Field(
        default=[5, 15, 60, 300]
    )
    AUTH_LOGIN_FAILURE_WINDOW_SECONDS: int = Field(default=900, ge=60)
    AUTH_LOGIN_DISTRIBUTED_EMAIL_LIMIT: int = Field(default=30, ge=1)
    AUTH_RATE_LIMIT_REGISTER: int = 5
    AUTH_RATE_LIMIT_FORGOT: int = 3
    AUTH_RATE_LIMIT_RESET: int = 5
    AUTH_RATE_LIMIT_VERIFY: int = 10
    AUTH_RATE_LIMIT_REFRESH: int = 30
    AUTH_RATE_LIMIT_ORG_INVITE: int = 20

    # -------------------------------------------------------------------------
    # Database - PostgreSQL
    # -------------------------------------------------------------------------
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "finsight"
    POSTGRES_PASSWORD: SecretStr = Field(default=...)
    POSTGRES_DB: str = "finsight"
    POSTGRES_SSL_MODE: str = Field(
        default="disable",
        pattern="^(disable|allow|prefer|require|verify-ca|verify-full)$",
    )
    POSTGRES_RLS_ROLE: str = Field(
        default="finsight_app",
        pattern="^[a-z_][a-z0-9_]*$",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def DATABASE_URL(self) -> PostgresDsn:
        """Build asyncpg connection URL from components (SSL is passed via connect_args)."""
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD.get_secret_value(),
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    # -------------------------------------------------------------------------
    # Redis
    # -------------------------------------------------------------------------
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: SecretStr = SecretStr("")
    REDIS_DB: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def REDIS_URL(self) -> RedisDsn:
        """Build Redis connection URL."""
        password = self.REDIS_PASSWORD.get_secret_value()
        if password:
            return RedisDsn.build(
                scheme="redis",
                username="",
                password=password,
                host=self.REDIS_HOST,
                port=self.REDIS_PORT,
                path=f"/{self.REDIS_DB}",
            )
        return RedisDsn.build(
            scheme="redis",
            host=self.REDIS_HOST,
            port=self.REDIS_PORT,
            path=f"/{self.REDIS_DB}",
        )

    # -------------------------------------------------------------------------
    # Qdrant - Vector Search
    # -------------------------------------------------------------------------
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: SecretStr = SecretStr("")
    QDRANT_COLLECTION_PREFIX: str = "finsight"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def QDRANT_URL(self) -> str:
        """Build Qdrant HTTP base URL."""
        return f"http://{self.QDRANT_HOST}:{self.QDRANT_PORT}"

    # -------------------------------------------------------------------------
    # S3-Compatible Object Storage - Garage / S3 / R2
    # -------------------------------------------------------------------------
    S3_HOST: str = "garage"
    S3_PORT: int = 3900
    S3_ADMIN_PORT: int = 3903
    S3_ACCESS_KEY: SecretStr = Field(default=...)
    S3_SECRET_KEY: SecretStr = Field(default=...)
    S3_BUCKET_DOCUMENTS: str = "finsight-documents"
    S3_BUCKET_REPORTS: str = "finsight-reports"
    S3_REGION: str = "us-east-1"
    S3_SECURE: bool = False
    GARAGE_ADMIN_TOKEN: SecretStr = SecretStr("")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def S3_ENDPOINT(self) -> str:
        """Host:port endpoint for MinIO/S3 SDK clients."""
        return f"{self.S3_HOST}:{self.S3_PORT}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def S3_ENDPOINT_URL(self) -> str:
        """Full HTTP(S) URL for S3-compatible object storage."""
        scheme = "https" if self.S3_SECURE else "http"
        return f"{scheme}://{self.S3_HOST}:{self.S3_PORT}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def S3_ADMIN_URL(self) -> str:
        """Full HTTP(S) URL for Garage Admin API."""
        scheme = "https" if self.S3_SECURE else "http"
        return f"{scheme}://{self.S3_HOST}:{self.S3_ADMIN_PORT}"

    # -------------------------------------------------------------------------
    # LLM Providers - optional for F0, required for F7+
    # -------------------------------------------------------------------------
    GROQ_API_KEY: SecretStr = SecretStr("")
    GROQ_DEFAULT_MODEL: str = "llama-3.1-70b-versatile"

    GEMINI_API_KEY: SecretStr = SecretStr("")
    GEMINI_DEFAULT_MODEL: str = "gemini-1.5-flash"

    OPENROUTER_API_KEY: SecretStr = SecretStr("")
    OPENROUTER_DEFAULT_MODEL: str = "anthropic/claude-3.5-sonnet"

    MISTRAL_API_KEY: SecretStr = SecretStr("")
    MISTRAL_DEFAULT_MODEL: str = "mistral-large-latest"

    CEREBRAS_API_KEY: SecretStr = SecretStr("")
    CEREBRAS_DEFAULT_MODEL: str = "llama3.1-70b"

    HF_API_KEY: SecretStr = SecretStr("")
    HF_DEFAULT_MODEL: str = "meta-llama/Meta-Llama-3.1-70B-Instruct"

    OLLAMA_HOST: str = "ollama"
    OLLAMA_PORT: int = 11434
    OLLAMA_DEFAULT_MODEL: str = "llama3.1:70b"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def OLLAMA_URL(self) -> str:
        """Build Ollama HTTP base URL."""
        return f"http://{self.OLLAMA_HOST}:{self.OLLAMA_PORT}"

    LLM_ROUTER_CONFIG_PATH: str = "./config/llm_router.yaml"

    # -------------------------------------------------------------------------
    # External Data Providers
    # -------------------------------------------------------------------------
    ALPHA_VANTAGE_API_KEY: SecretStr = SecretStr("")
    NEWS_API_KEY: SecretStr = SecretStr("")
    FINBERT_MODEL: str = "ProsusAI/finbert"

    # -------------------------------------------------------------------------
    # Billing - TEST MODE ONLY
    # -------------------------------------------------------------------------
    BILLING_PROVIDER: str = "stripe"
    STRIPE_SECRET_KEY: SecretStr = SecretStr("")
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: SecretStr = SecretStr("")
    STRIPE_API_VERSION: str = "2024-04-10"

    # -------------------------------------------------------------------------
    # LangSmith - Observability
    # -------------------------------------------------------------------------
    LANGSMITH_API_KEY: SecretStr = SecretStr("")
    LANGSMITH_PROJECT: str = "finsight-dev"
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"

    # -------------------------------------------------------------------------
    # Email
    # -------------------------------------------------------------------------
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: SecretStr = SecretStr("")
    SMTP_FROM: str = "noreply@finsight.local"
    SMTP_USE_STARTTLS: bool = True
    SMTP_USE_SSL: bool = False
    SMTP_TIMEOUT_SECONDS: int = 10
    EMAIL_VERIFICATION_BASE_URL: str = "http://localhost:3000/verify-email"
    PASSWORD_RESET_BASE_URL: str = "http://localhost:3000/reset-password"
    INVITATION_ACCEPT_BASE_URL: str = "http://localhost:3000/invitations/accept"

    # -------------------------------------------------------------------------
    # Google OAuth
    # -------------------------------------------------------------------------
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: SecretStr = SecretStr("")
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"
    GOOGLE_OAUTH_TIMEOUT_SECONDS: int = 10

    # -------------------------------------------------------------------------
    # Demo Request
    # -------------------------------------------------------------------------
    DEMO_REQUEST_WEBHOOK_URL: str = ""
    DEMO_REQUEST_EMAIL_TO: str = ""

    # -------------------------------------------------------------------------
    # Admin
    # -------------------------------------------------------------------------
    ADMIN_EMAIL: str = "admin@finsight.local"
    ADMIN_PASSWORD: SecretStr = Field(default=...)

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Reject weak or placeholder secrets in staging/production."""
        has_google_id = bool(self.GOOGLE_CLIENT_ID.strip())
        has_google_secret = bool(self.GOOGLE_CLIENT_SECRET.get_secret_value().strip())
        if has_google_id != has_google_secret:
            raise ValueError(
                "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must both be set or both empty"
            )

        if self.APP_ENV in ("staging", "production"):
            secret = self.SECRET_KEY.get_secret_value()
            if len(secret) < MIN_SECRET_KEY_LENGTH or secret.startswith(("CHANGE_ME", "dev-")):
                raise ValueError("SECRET_KEY must be a strong 32+ char key in staging/production")
            if self.ADMIN_PASSWORD.get_secret_value().startswith("CHANGE_ME"):
                raise ValueError(
                    "ADMIN_PASSWORD must not use placeholder value in staging/production"
                )
            if not self.FRONTEND_URL.startswith("https://"):
                raise ValueError("FRONTEND_URL must use https:// in staging/production")
            if self.RATE_LIMIT_PROFILE == "relaxed_dev":
                raise ValueError(
                    "RATE_LIMIT_PROFILE must be 'strict' (or 'auto') in staging/production"
                )
            if not self.RATE_LIMIT_ENABLED:
                raise ValueError("RATE_LIMIT_ENABLED must be true in staging/production")
            for cidr in self.TRUSTED_PROXY_CIDRS:
                try:
                    net = ipaddress.ip_network(cidr, strict=False)
                except ValueError as exc:
                    raise ValueError(f"Invalid CIDR '{cidr}' in TRUSTED_PROXY_CIDRS") from exc
                is_broad_v4 = (
                    net.version == _IPV4_VERSION
                    and net.prefixlen < _MIN_PROD_PROXY_IPV4_PREFIX
                    and not net.is_loopback
                )
                is_broad_v6 = (
                    net.version == _IPV6_VERSION
                    and net.prefixlen < _MIN_PROD_PROXY_IPV6_PREFIX
                    and not net.is_loopback
                )
                if (
                    net.prefixlen == 0
                    or net in _BROAD_PRIVATE_PROXY_NETS
                    or is_broad_v4
                    or is_broad_v6
                ):
                    raise ValueError(
                        "TRUSTED_PROXY_CIDRS must be restricted to explicit reverse-proxy "
                        "IPs/subnets in staging/production"
                    )
        return self

    @property
    def effective_rate_limit_profile(self) -> Literal["relaxed_dev", "strict"]:
        """Resolve effective rate-limiting profile (always strict in staging/production)."""
        if self.APP_ENV in ("staging", "production"):
            return "strict"
        if self.RATE_LIMIT_PROFILE == "strict":
            return "strict"
        if self.RATE_LIMIT_PROFILE == "relaxed_dev":
            return "relaxed_dev"
        return "relaxed_dev" if self.APP_ENV == "development" else "strict"

    @property
    def auth_cookie_secure(self) -> bool:
        """Return whether auth cookies must have the Secure flag set."""
        if self.AUTH_COOKIE_SECURE is not None:
            return self.AUTH_COOKIE_SECURE
        return self.APP_ENV in ("staging", "production")

    @property
    def google_oauth_enabled(self) -> bool:
        """Return True when both Google OAuth credentials are configured."""
        return bool(
            self.GOOGLE_CLIENT_ID.strip() and self.GOOGLE_CLIENT_SECRET.get_secret_value().strip()
        )

    # -------------------------------------------------------------------------
    # Validation helpers
    # -------------------------------------------------------------------------
    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.APP_ENV == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance. Raises ValidationError if required vars missing."""
    return Settings()  # type: ignore[call-arg]
