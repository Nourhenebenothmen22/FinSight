"""Pytest configuration and fixtures for backend tests."""

from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass, field
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.queue import TaskDispatcher, get_task_dispatcher
from app.core.redis import get_redis
from app.main import app as fastapi_app
from app.models.base import Base


class InMemoryRedisStub:
    """Minimal async Redis stub supporting get, set, delete, and F1 Lua scripts."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        _ = ex
        self._store[key] = value
        return True

    async def delete(self, key: str) -> int:
        return 1 if self._store.pop(key, None) is not None else 0

    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> Any:
        _ = numkeys
        key = keys_and_args[0]
        if "INCR" in script:
            window = int(keys_and_args[1]) if len(keys_and_args) > 1 else 60
            current = int(self._store.get(key, "0")) + 1
            self._store[key] = str(current)
            return [current, window]
        if "GET" in script and "DEL" in script:
            return self._store.pop(key, None)
        raise NotImplementedError("Unsupported Lua script in InMemoryRedisStub")


@dataclass
class RecordedJob:
    """Recorded background task invocation for assertions in auth tests."""

    task_name: str
    args: tuple[object, ...]


@dataclass
class RecordingTaskDispatcher(TaskDispatcher):
    """In-memory TaskDispatcher recording ARQ jobs dispatched during tests."""

    jobs: list[RecordedJob] = field(default_factory=list)

    async def enqueue(self, task_name: str, *args: object) -> None:
        self.jobs.append(RecordedJob(task_name=task_name, args=args))


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
        RATE_LIMIT_ENABLED=True,
    )


@pytest.fixture(scope="function")
def fake_redis() -> InMemoryRedisStub:
    """Isolated in-memory Redis stub per test."""
    return InMemoryRedisStub()


@pytest.fixture(scope="function")
def task_dispatcher() -> RecordingTaskDispatcher:
    """Isolated in-memory ARQ task recorder per test."""
    return RecordingTaskDispatcher()


# -----------------------------------------------------------------------------
# Database Fixtures
# -----------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create test database engine (SQLite in-memory with StaticPool)."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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
def test_app(
    test_db: AsyncSession,
    fake_redis: InMemoryRedisStub,
    task_dispatcher: RecordingTaskDispatcher,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[FastAPI, None, None]:
    """Create a test FastAPI app with overridden DB, Redis, queue, and settings."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-testing-only-32chars")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test")
    monkeypatch.setenv("S3_ACCESS_KEY", "GK000000000000000000000000")
    monkeypatch.setenv("S3_SECRET_KEY", "0" * 64)
    monkeypatch.setenv("ADMIN_PASSWORD", "testadminpassword")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "")
    monkeypatch.setenv("SMTP_HOST", "")
    get_settings.cache_clear()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield test_db

    async def override_get_redis() -> InMemoryRedisStub:
        return fake_redis

    async def override_get_dispatcher() -> RecordingTaskDispatcher:
        return task_dispatcher

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_redis] = override_get_redis
    fastapi_app.dependency_overrides[get_task_dispatcher] = override_get_dispatcher
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()
    get_settings.cache_clear()


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
