"""Tenant-scoped audit logging service (F2)."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import AuditLog


async def record_audit_event(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    action: str,
    target: str,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Persist an immutable audit log entry within an organization."""
    entry = AuditLog(
        org_id=org_id,
        actor_id=actor_id,
        action=action,
        target=target[:255],
        event_metadata=metadata or {},
    )
    db.add(entry)
    await db.flush()
    return entry
