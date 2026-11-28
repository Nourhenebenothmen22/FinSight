"""Tenant workspace, RBAC membership, email invitation, and audit log services (F2)."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from fastapi import HTTPException, status
from slugify import slugify  # type: ignore[import-untyped]
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.queue import TaskDispatcher
from app.core.security import generate_opaque_token, hash_token
from app.models.auth import User
from app.models.tenant import (
    AuditLog,
    Membership,
    Organization,
    OrganizationInvitation,
    OrgRole,
)
from app.schemas.tenant import (
    AuditLogListResponse,
    AuditLogResponse,
    CreateInvitationRequest,
    CreateOrganizationRequest,
    InvitationResponse,
    MemberResponse,
    OrganizationSummaryResponse,
    UpdateMemberRoleRequest,
    UpdateOrganizationRequest,
)
from app.services.audit import record_audit_event
from app.services.email import build_action_url

logger = structlog.get_logger(__name__)

_MAX_ORG_NAME_LEN = 120
_MAX_SLUG_BASE_LEN = 100


def _ensure_utc(dt: datetime) -> datetime:
    """Normalize naive datetimes (e.g. SQLite unit tests) to UTC-aware datetimes."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


async def _generate_unique_slug(db: AsyncSession, raw_name: str) -> str:
    """Generate a unique URL-safe slug from an organization name."""
    base = slugify(raw_name, max_length=_MAX_SLUG_BASE_LEN) or "workspace"
    candidate = base
    for _ in range(5):
        existing = await db.execute(select(Organization.id).where(Organization.slug == candidate))
        if existing.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base}-{secrets.token_hex(4)}"
    return f"ws-{uuid.uuid4().hex[:12]}"


def _to_org_summary(org: Organization, role: str) -> OrganizationSummaryResponse:
    """Convert Organization + Membership role into OrganizationSummaryResponse."""
    return OrganizationSummaryResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        owner_id=org.owner_id,
        plan_id=org.plan_id,
        role=OrgRole(role),
        created_at=org.created_at,
    )


async def create_organization_with_owner(
    db: AsyncSession,
    *,
    owner: User,
    name: str,
    actor_id: uuid.UUID | None,
    reason: str,
) -> OrganizationSummaryResponse:
    """Create a tenant organization, accepted owner membership, and initial audit event."""
    now = datetime.now(UTC)
    clean_name = name.strip()[:_MAX_ORG_NAME_LEN] or "My Workspace"
    slug = await _generate_unique_slug(db, clean_name)

    org = Organization(
        name=clean_name,
        slug=slug,
        owner_id=owner.id,
        plan_id=None,
    )
    db.add(org)
    await db.flush()

    membership = Membership(
        org_id=org.id,
        user_id=owner.id,
        role=OrgRole.OWNER,
        invited_by_id=owner.id,
        invited_at=now,
        accepted_at=now,
    )
    db.add(membership)
    await db.flush()

    await record_audit_event(
        db,
        org_id=org.id,
        actor_id=actor_id,
        action="org.created",
        target=f"org:{org.id}",
        metadata={"reason": reason, "slug": org.slug},
    )
    return _to_org_summary(org, OrgRole.OWNER)


async def create_personal_organization_for_user(
    db: AsyncSession,
    user: User,
) -> OrganizationSummaryResponse:
    """Provision the default personal organization upon user signup."""
    personal_name = f"{user.name}'s Workspace"[:_MAX_ORG_NAME_LEN]
    return await create_organization_with_owner(
        db,
        owner=user,
        name=personal_name,
        actor_id=user.id,
        reason="signup_auto_provision",
    )


async def list_user_organizations(
    db: AsyncSession,
    user: User,
) -> list[OrganizationSummaryResponse]:
    """List all organizations where the user holds an accepted membership."""
    stmt = (
        select(Organization, Membership.role)
        .join(Membership, Membership.org_id == Organization.id)
        .where(Membership.user_id == user.id, Membership.accepted_at.is_not(None))
        .order_by(Organization.created_at.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [_to_org_summary(org, role) for org, role in rows]


async def create_organization(
    db: AsyncSession,
    user: User,
    payload: CreateOrganizationRequest,
) -> OrganizationSummaryResponse:
    """Create a new workspace owned by the authenticated user."""
    summary = await create_organization_with_owner(
        db,
        owner=user,
        name=payload.name,
        actor_id=user.id,
        reason="user_created",
    )
    await db.commit()
    logger.info("org.created", org_id=str(summary.id), owner_id=str(user.id))
    return summary


async def update_organization(
    db: AsyncSession,
    *,
    org: Organization,
    actor: User,
    role: OrgRole,
    payload: UpdateOrganizationRequest,
) -> OrganizationSummaryResponse:
    """Update organization attributes (owner-only enforced by route dependency)."""
    previous_name = org.name
    org.name = payload.name
    await record_audit_event(
        db,
        org_id=org.id,
        actor_id=actor.id,
        action="org.updated",
        target=f"org:{org.id}",
        metadata={"previous_name": previous_name, "new_name": payload.name},
    )
    await db.commit()
    await db.refresh(org)
    return _to_org_summary(org, role)


async def list_members(db: AsyncSession, org_id: uuid.UUID) -> list[MemberResponse]:
    """List active members of an organization."""
    stmt = (
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.org_id == org_id, Membership.accepted_at.is_not(None))
        .order_by(Membership.created_at.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        MemberResponse(
            user_id=user.id,
            email=user.email,
            name=user.name,
            role=OrgRole(membership.role),
            invited_at=membership.invited_at,
            accepted_at=membership.accepted_at,
        )
        for membership, user in rows
    ]


async def _count_org_owners(db: AsyncSession, org_id: uuid.UUID) -> int:
    """Return the count of accepted owners inside an organization."""
    stmt = select(func.count(Membership.id)).where(
        Membership.org_id == org_id,
        Membership.role == OrgRole.OWNER,
        Membership.accepted_at.is_not(None),
    )
    count = (await db.execute(stmt)).scalar_one()
    return int(count)


async def _ensure_org_owner_id_points_to_active_owner(
    db: AsyncSession,
    org: Organization,
    excluding_user_id: uuid.UUID,
) -> None:
    """Update Organization.owner_id to another remaining owner before removing/demoting owner_id."""
    if org.owner_id != excluding_user_id:
        return
    replacement_stmt = (
        select(Membership.user_id)
        .where(
            Membership.org_id == org.id,
            Membership.role == OrgRole.OWNER,
            Membership.accepted_at.is_not(None),
            Membership.user_id != excluding_user_id,
        )
        .limit(1)
    )
    replacement_id = (await db.execute(replacement_stmt)).scalar_one_or_none()
    if replacement_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization must retain at least one owner",
        )
    org.owner_id = replacement_id


async def _lock_organization(db: AsyncSession, org_id: uuid.UUID) -> None:
    """Serialize membership role/removal mutations per organization on PostgreSQL."""
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        await db.execute(select(Organization.id).where(Organization.id == org_id).with_for_update())


async def update_member_role(
    db: AsyncSession,
    *,
    org: Organization,
    actor: User,
    target_user_id: uuid.UUID,
    payload: UpdateMemberRoleRequest,
) -> MemberResponse:
    """Update a member's RBAC role while protecting the last owner."""
    await _lock_organization(db, org.id)
    stmt = (
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.org_id == org.id,
            Membership.user_id == target_user_id,
            Membership.accepted_at.is_not(None),
        )
    )
    row = (await db.execute(stmt)).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    membership, target_user = row
    previous_role = OrgRole(membership.role)
    if previous_role == payload.role:
        return MemberResponse(
            user_id=target_user.id,
            email=target_user.email,
            name=target_user.name,
            role=payload.role,
            invited_at=membership.invited_at,
            accepted_at=membership.accepted_at,
        )

    if previous_role == OrgRole.OWNER and payload.role != OrgRole.OWNER:
        owner_count = await _count_org_owners(db, org.id)
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot demote the sole owner of the organization",
            )
        await _ensure_org_owner_id_points_to_active_owner(db, org, target_user_id)

    membership.role = payload.role.value
    await record_audit_event(
        db,
        org_id=org.id,
        actor_id=actor.id,
        action="member.role_updated",
        target=f"user:{target_user_id}",
        metadata={"previous_role": previous_role.value, "new_role": payload.role.value},
    )
    await db.commit()
    return MemberResponse(
        user_id=target_user.id,
        email=target_user.email,
        name=target_user.name,
        role=payload.role,
        invited_at=membership.invited_at,
        accepted_at=membership.accepted_at,
    )


async def remove_member(
    db: AsyncSession,
    *,
    org: Organization,
    actor: User,
    target_user_id: uuid.UUID,
) -> None:
    """Remove a member from an organization while blocking sole-owner removal."""
    await _lock_organization(db, org.id)
    stmt = select(Membership).where(
        Membership.org_id == org.id,
        Membership.user_id == target_user_id,
        Membership.accepted_at.is_not(None),
    )
    membership = (await db.execute(stmt)).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if membership.role == OrgRole.OWNER:
        owner_count = await _count_org_owners(db, org.id)
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot remove the sole owner of the organization",
            )
        await _ensure_org_owner_id_points_to_active_owner(db, org, target_user_id)

    removed_role = membership.role
    await db.delete(membership)
    await record_audit_event(
        db,
        org_id=org.id,
        actor_id=actor.id,
        action="member.removed",
        target=f"user:{target_user_id}",
        metadata={"role": removed_role},
    )
    await db.commit()


async def leave_organization(
    db: AsyncSession,
    *,
    org: Organization,
    membership: Membership,
    actor: User,
) -> None:
    """Allow a member to leave an organization (unless they are the sole owner)."""
    await _lock_organization(db, org.id)
    if membership.role == OrgRole.OWNER:
        owner_count = await _count_org_owners(db, org.id)
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sole owner cannot leave organization; transfer ownership first",
            )
        await _ensure_org_owner_id_points_to_active_owner(db, org, actor.id)

    left_role = membership.role
    await db.delete(membership)
    await record_audit_event(
        db,
        org_id=org.id,
        actor_id=actor.id,
        action="member.left",
        target=f"user:{actor.id}",
        metadata={"role": left_role},
    )
    await db.commit()


async def create_invitation(
    db: AsyncSession,
    *,
    org: Organization,
    actor: User,
    payload: CreateInvitationRequest,
    settings: Settings,
    dispatcher: TaskDispatcher,
) -> InvitationResponse:
    """Create a pending email invitation and enqueue delivery via ARQ."""
    existing_member_stmt = (
        select(Membership.id)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.org_id == org.id,
            User.email == payload.email,
            Membership.accepted_at.is_not(None),
        )
    )
    if (await db.execute(existing_member_stmt)).scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this organization",
        )

    now = datetime.now(UTC)
    await db.execute(
        update(OrganizationInvitation)
        .where(
            OrganizationInvitation.org_id == org.id,
            OrganizationInvitation.email == payload.email,
            OrganizationInvitation.accepted_at.is_(None),
            OrganizationInvitation.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )

    raw_token = generate_opaque_token()
    invitation = OrganizationInvitation(
        org_id=org.id,
        email=payload.email,
        role=payload.role.value,
        token_hash=hash_token(raw_token),
        invited_by_id=actor.id,
        expires_at=now + timedelta(days=settings.ORG_INVITATION_EXPIRE_DAYS),
    )
    db.add(invitation)
    await db.flush()

    await record_audit_event(
        db,
        org_id=org.id,
        actor_id=actor.id,
        action="member.invited",
        target=f"invitation:{invitation.id}",
        metadata={"role": payload.role.value, "email_hash": hash_token(payload.email)},
    )

    accept_url = build_action_url(settings.INVITATION_ACCEPT_BASE_URL, raw_token)
    try:
        await dispatcher.enqueue(
            "send_org_invitation_email_task",
            {
                "to_email": payload.email,
                "inviter_name": actor.name,
                "org_name": org.name,
                "role": payload.role.value,
                "accept_url": accept_url,
            },
        )
    except Exception as exc:
        logger.exception("org.invitation_enqueue_failed", org_id=str(org.id))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email notification service is temporarily unavailable",
        ) from exc

    await db.commit()
    await db.refresh(invitation)
    return InvitationResponse.model_validate(invitation)


async def list_invitations(db: AsyncSession, org_id: uuid.UUID) -> list[InvitationResponse]:
    """List pending invitations for an organization."""
    now = datetime.now(UTC)
    stmt = (
        select(OrganizationInvitation)
        .where(
            OrganizationInvitation.org_id == org_id,
            OrganizationInvitation.accepted_at.is_(None),
            OrganizationInvitation.revoked_at.is_(None),
            OrganizationInvitation.expires_at > now,
        )
        .order_by(OrganizationInvitation.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [InvitationResponse.model_validate(row) for row in rows]


async def revoke_invitation(
    db: AsyncSession,
    *,
    org: Organization,
    actor: User,
    invitation_id: uuid.UUID,
) -> None:
    """Revoke a pending organization invitation."""
    now = datetime.now(UTC)
    stmt = (
        select(OrganizationInvitation)
        .where(
            OrganizationInvitation.id == invitation_id,
            OrganizationInvitation.org_id == org.id,
            OrganizationInvitation.accepted_at.is_(None),
            OrganizationInvitation.revoked_at.is_(None),
        )
        .limit(1)
    )
    invitation = (await db.execute(stmt)).scalar_one_or_none()
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    invitation.revoked_at = now
    await record_audit_event(
        db,
        org_id=org.id,
        actor_id=actor.id,
        action="member.invitation_revoked",
        target=f"invitation:{invitation.id}",
        metadata={"role": invitation.role},
    )
    await db.commit()


async def accept_invitation(
    db: AsyncSession,
    *,
    user: User,
    raw_token: str,
) -> OrganizationSummaryResponse:
    """Validate an invitation token against the signed-in user's verified email and join."""
    now = datetime.now(UTC)
    token_hash = hash_token(raw_token)
    stmt = select(OrganizationInvitation).where(OrganizationInvitation.token_hash == token_hash)
    invitation = (await db.execute(stmt)).scalar_one_or_none()

    if (
        invitation is None
        or invitation.revoked_at is not None
        or invitation.accepted_at is not None
        or _ensure_utc(invitation.expires_at) <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation token is invalid or expired",
        )

    if user.email_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify your email address before accepting an organization invitation",
        )

    if user.email.strip().lower() != invitation.email.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation was issued for a different email address",
        )

    existing_member = (
        await db.execute(
            select(Membership).where(
                Membership.org_id == invitation.org_id,
                Membership.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if existing_member is not None and existing_member.accepted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already a member of this organization",
        )

    consumed: Any = await db.execute(
        update(OrganizationInvitation)
        .where(
            OrganizationInvitation.id == invitation.id,
            OrganizationInvitation.accepted_at.is_(None),
            OrganizationInvitation.revoked_at.is_(None),
        )
        .values(accepted_at=now)
    )
    if getattr(consumed, "rowcount", 0) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation token has already been used",
        )

    if existing_member is None:
        membership = Membership(
            org_id=invitation.org_id,
            user_id=user.id,
            role=invitation.role,
            invited_by_id=invitation.invited_by_id,
            invited_at=invitation.created_at,
            accepted_at=now,
        )
        db.add(membership)
    else:
        existing_member.role = invitation.role
        existing_member.accepted_at = now

    org = (
        await db.execute(select(Organization).where(Organization.id == invitation.org_id))
    ).scalar_one()

    await record_audit_event(
        db,
        org_id=org.id,
        actor_id=user.id,
        action="member.joined",
        target=f"user:{user.id}",
        metadata={"role": invitation.role, "invitation_id": str(invitation.id)},
    )
    await db.commit()
    logger.info("org.member_joined", org_id=str(org.id), user_id=str(user.id))
    return _to_org_summary(org, invitation.role)


async def list_audit_logs(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    limit: int = 50,
    offset: int = 0,
) -> AuditLogListResponse:
    """List paginated tenant audit log entries."""
    total_stmt = select(func.count(AuditLog.id)).where(AuditLog.org_id == org_id)
    total = int((await db.execute(total_stmt)).scalar_one())

    stmt = (
        select(AuditLog)
        .where(AuditLog.org_id == org_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).scalars().all()
    items = [
        AuditLogResponse(
            id=row.id,
            org_id=row.org_id,
            actor_id=row.actor_id,
            action=row.action,
            target=row.target,
            metadata=dict(row.event_metadata),
            created_at=row.created_at,
        )
        for row in rows
    ]
    return AuditLogListResponse(items=items, total=total, limit=limit, offset=offset)
