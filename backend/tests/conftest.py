"""Pytest configuration and fixtures for backend tests."""

import math
import time
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
    """Minimal async Redis stub supporting TTLs, GET/SET/DELETE, and FinSight Lua scripts."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._expires_at_ms: dict[str, int] = {}

    def _prune(self, key: str, now_ms: int | None = None) -> None:
        exp = self._expires_at_ms.get(key)
        if exp is None:
            return
        current_ms = int(time.time() * 1000) if now_ms is None else now_ms
        if current_ms >= exp:
            self._store.pop(key, None)
            self._expires_at_ms.pop(key, None)

    async def get(self, key: str) -> str | None:
        self._prune(key)
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self._store[key] = value
        if ex is not None:
            self._expires_at_ms[key] = int(time.time() * 1000) + int(ex) * 1000
        else:
            self._expires_at_ms.pop(key, None)
        return True

    async def delete(self, key: str) -> int:
        self._expires_at_ms.pop(key, None)
        return 1 if self._store.pop(key, None) is not None else 0

    def _eval_token_bucket(self, key: str, args: tuple[str, ...]) -> list[int]:
        capacity = int(args[0])
        refill_per_sec = float(args[1])
        now_ms = int(args[2])
        ttl_ms = int(args[3])
        self._prune(key, now_ms)

        tokens = float(capacity)
        last_ms = now_ms
        raw = self._store.get(key)
        if raw and ":" in raw:
            tok_str, ts_str = raw.split(":", maxsplit=1)
            tokens = float(tok_str)
            last_ms = int(ts_str)

        elapsed = max(0.0, (now_ms - last_ms) / 1000.0)
        tokens = min(float(capacity), tokens + elapsed * refill_per_sec)
        if tokens >= 1.0:
            tokens -= 1.0
            self._store[key] = f"{tokens:.9f}:{now_ms}"
            self._expires_at_ms[key] = now_ms + ttl_ms
            return [1, math.floor(tokens), 0]

        needed = 1.0 - tokens
        retry_after = max(1, math.ceil(needed / refill_per_sec))
        self._store[key] = f"{tokens:.9f}:{now_ms}"
        self._expires_at_ms[key] = now_ms + ttl_ms
        return [0, 0, retry_after]

    def _eval_login_cooldown_check(self, keys: tuple[str, ...], args: tuple[str, ...]) -> list[int]:
        now_ms = int(args[0])
        max_retry_sec = 0
        blocking_idx = 0
        for idx, key in enumerate(keys, start=1):
            self._prune(key, now_ms)
            raw = self._store.get(key)
            if raw and ":" in raw:
                _, blocked_str = raw.split(":", maxsplit=1)
                blocked_until = int(blocked_str)
                if blocked_until > now_ms:
                    retry_sec = max(1, math.ceil((blocked_until - now_ms) / 1000.0))
                    if retry_sec > max_retry_sec:
                        max_retry_sec = retry_sec
                        blocking_idx = idx
        return [max_retry_sec, blocking_idx]

    def _eval_login_failure(self, key: str, args: tuple[str, ...]) -> list[int]:
        free_attempts = int(args[0])
        window_ms = int(args[1])
        now_ms = int(args[2])
        steps = [int(item) for item in args[3:]]
        self._prune(key, now_ms)

        count = 0
        blocked_until_ms = 0
        raw = self._store.get(key)
        if raw and ":" in raw:
            count_str, blocked_str = raw.split(":", maxsplit=1)
            count = int(count_str)
            blocked_until_ms = int(blocked_str)

        count += 1
        penalty_sec = 0
        if count >= free_attempts and steps:
            step_idx = min(count - free_attempts, len(steps) - 1)
            penalty_sec = steps[step_idx]
            blocked_until_ms = max(blocked_until_ms, now_ms + penalty_sec * 1000)

        ttl_ms = max(window_ms, penalty_sec * 1000 + 1000)
        self._store[key] = f"{count}:{blocked_until_ms}"
        self._expires_at_ms[key] = now_ms + ttl_ms
        return [count, blocked_until_ms, penalty_sec]

    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> Any:
        keys = keys_and_args[:numkeys]
        args = keys_and_args[numkeys:]

        if "FINSIGHT_LUA:token_bucket" in script:
            return self._eval_token_bucket(keys[0], args)
        if "FINSIGHT_LUA:login_cooldown_check" in script:
            return self._eval_login_cooldown_check(keys, args)
        if "FINSIGHT_LUA:login_failure" in script:
            return self._eval_login_failure(keys[0], args)

        key = keys_and_args[0]
        if "GET" in script and "DEL" in script:
            self._prune(key)
            self._expires_at_ms.pop(key, None)
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
        FRONTEND_URL="http://localhost:3000",
        CORS_ORIGINS=["http://localhost:3000"],
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
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:3000")
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
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
