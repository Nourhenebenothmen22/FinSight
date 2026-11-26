"""Pytest configuration and fixtures for backend tests."""

from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.database import get_db
from app.main import app as fastapi_app
from app.models.base import Base


# -----------------------------------------------------------------------------
# Test Settings
# -----------------------------------------------------------------------------
@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Test settings with isolated test configuration."""
    return Settings(
        APP_ENV="test",
        SECRET_KEY="test-secret-key-for-testing-only-32chars",
        POSTGRES_HOST="localhost",
        POSTGRES_PORT=5432,
        POSTGRES_USER="test",
        POSTGRES_PASSWORD="test",
        POSTGRES_DB="test",
        POSTGRES_SSL_MODE="disable",
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        REDIS_PASSWORD="",
        REDIS_DB=1,
        QDRANT_HOST="localhost",
        QDRANT_PORT=6333,
        QDRANT_API_KEY="",
        S3_HOST="localhost",
        S3_PORT=3900,
        S3_ADMIN_PORT=3903,
        S3_ACCESS_KEY="GK000000000000000000000000",
        S3_SECRET_KEY="0" * 64,
        S3_BUCKET_DOCUMENTS="test-documents",
        S3_BUCKET_REPORTS="test-reports",
        ADMIN_PASSWORD="testadminpassword",
    )


# -----------------------------------------------------------------------------
# Database Fixtures
# -----------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create test database engine (SQLite in-memory for speed)."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=NullPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_session_factory(test_engine):
    """Create test session factory."""
    return async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


@pytest_asyncio.fixture(scope="function")
async def test_db(test_session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Get a test database session."""
    async with test_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# -----------------------------------------------------------------------------
# FastAPI App Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture(scope="function")
def test_app(test_db: AsyncSession) -> Generator[FastAPI, None, None]:
    """Create a test FastAPI app with overridden dependencies."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield test_db

    fastapi_app.dependency_overrides[get_db] = override_get_db
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def client(test_app: FastAPI) -> Generator[TestClient, None, None]:
    """Test client for synchronous tests."""
    with TestClient(test_app) as test_client:
        yield test_client


@pytest_asyncio.fixture(scope="function")
async def async_client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Async test client for async tests."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
