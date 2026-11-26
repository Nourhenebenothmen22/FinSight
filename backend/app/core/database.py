"""Database configuration: SQLAlchemy async engine, session management."""

import re
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.models.base import Base

__all__ = [
    "Base",
    "bind_tenant_rls",
    "close_db",
    "get_db",
    "get_engine",
    "get_session",
    "get_session_factory",
    "init_db",
]

_VALID_PG_ROLE_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass
class _DatabaseState:
    engine: AsyncEngine | None = None
    session_factory: async_sessionmaker[AsyncSession] | None = None


_state = _DatabaseState()


def get_engine() -> AsyncEngine:
    """Get or create the async SQLAlchemy engine."""
    if _state.engine is None:
        settings = get_settings()
        connect_args: dict[str, Any] = {}
        if settings.POSTGRES_SSL_MODE != "disable":
            connect_args["ssl"] = settings.POSTGRES_SSL_MODE
        _state.engine = create_async_engine(
            str(settings.DATABASE_URL),
            echo=settings.is_development,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            pool_timeout=30,
            pool_recycle=3600,
            connect_args=connect_args,
        )
    return _state.engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory."""
    if _state.session_factory is None:
        _state.session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _state.session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session (async context manager)."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database session."""
    async with get_session() as session:
        yield session


async def bind_tenant_rls(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rls_role: str = "finsight_app",
) -> None:
    """Bind transaction-local tenant_id and non-superuser RLS role in PostgreSQL."""
    if not _VALID_PG_ROLE_RE.fullmatch(rls_role):
        raise ValueError("Invalid PostgreSQL RLS role identifier")

    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Both SET LOCAL ROLE and is_local=true revert automatically at transaction end
    await session.execute(text(f"SET LOCAL ROLE {rls_role}"))
    await session.execute(
        text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


async def init_db() -> None:
    """Initialize database tables in development if needed.

    Note: In production, use Alembic migrations instead.
    """
    import app.models  # noqa: F401, PLC0415

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections and reset session factory."""
    if _state.engine is not None:
        await _state.engine.dispose()
        _state.engine = None
    _state.session_factory = None
