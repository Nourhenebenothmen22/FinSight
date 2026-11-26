"""Application configuration using Pydantic Settings.

All settings are loaded from environment variables with validation at startup.
Required variables will raise ValidationError if missing.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

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
    EMAIL_VERIFICATION_BASE_URL: str = "http://localhost:3000/verify-email"
    PASSWORD_RESET_BASE_URL: str = "http://localhost:3000/reset-password"

    # -------------------------------------------------------------------------
    # Google OAuth
    # -------------------------------------------------------------------------
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: SecretStr = SecretStr("")
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"

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
        if self.APP_ENV in ("staging", "production"):
            secret = self.SECRET_KEY.get_secret_value()
            if len(secret) < MIN_SECRET_KEY_LENGTH or secret.startswith(("CHANGE_ME", "dev-")):
                raise ValueError("SECRET_KEY must be a strong 32+ char key in staging/production")
            if self.ADMIN_PASSWORD.get_secret_value().startswith("CHANGE_ME"):
                raise ValueError(
                    "ADMIN_PASSWORD must not use placeholder value in staging/production"
                )
        return self

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
