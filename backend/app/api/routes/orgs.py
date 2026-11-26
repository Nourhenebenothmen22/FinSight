"""Multi-tenant organization, membership, invitation, and audit log endpoints (F2)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, get_current_user, get_tenant_db, require_org_roles
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.queue import TaskDispatcher, get_task_dispatcher
from app.core.rate_limit import rate_limit
from app.models.auth import User
from app.models.tenant import OrgRole
from app.schemas.auth import MessageResponse
from app.schemas.tenant import (
    AcceptInvitationRequest,
    AuditLogListResponse,
    CreateInvitationRequest,
    CreateOrganizationRequest,
    InvitationResponse,
    MemberResponse,
    OrganizationSummaryResponse,
    UpdateMemberRoleRequest,
    UpdateOrganizationRequest,
)
from app.services import tenant as tenant_service

orgs_router = APIRouter(prefix="/api/v1/orgs", tags=["organizations"])
invitations_router = APIRouter(prefix="/api/v1/invitations", tags=["invitations"])

_FIFTEEN_MINUTES = 900


@orgs_router.get(
    "",
    response_model=list[OrganizationSummaryResponse],
    status_code=status.HTTP_200_OK,
    summary="List organizations the authenticated user belongs to",
)
async def list_my_organizations(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[OrganizationSummaryResponse]:
    """Return all workspaces where the user holds an accepted membership."""
    return await tenant_service.list_user_organizations(db, current_user)


@orgs_router.post(
    "",
    response_model=OrganizationSummaryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new organization workspace",
)
async def create_org(
    payload: CreateOrganizationRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationSummaryResponse:
    """Create a new workspace owned by the current user."""
    return await tenant_service.create_organization(db, current_user, payload)


@orgs_router.get(
    "/{org_id}",
    response_model=OrganizationSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get organization details",
)
async def get_org(
    tenant: Annotated[
        TenantContext,
        Depends(require_org_roles(OrgRole.OWNER, OrgRole.ANALYST, OrgRole.VIEWER)),
    ],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> OrganizationSummaryResponse:
    """Return organization summary if the user is a member."""
    _ = db
    org = tenant.organization
    return OrganizationSummaryResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        owner_id=org.owner_id,
        plan_id=org.plan_id,
        role=tenant.role,
        created_at=org.created_at,
    )


@orgs_router.patch(
    "/{org_id}",
    response_model=OrganizationSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Update organization settings (owner only)",
)
async def update_org(
    payload: UpdateOrganizationRequest,
    tenant: Annotated[TenantContext, Depends(require_org_roles(OrgRole.OWNER))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> OrganizationSummaryResponse:
    """Rename the organization (owner role required)."""
    return await tenant_service.update_organization(
        db,
        org=tenant.organization,
        actor=tenant.user,
        role=tenant.role,
        payload=payload,
    )


@orgs_router.get(
    "/{org_id}/members",
    response_model=list[MemberResponse],
    status_code=status.HTTP_200_OK,
    summary="List organization members",
)
async def get_members(
    tenant: Annotated[
        TenantContext,
        Depends(require_org_roles(OrgRole.OWNER, OrgRole.ANALYST, OrgRole.VIEWER)),
    ],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> list[MemberResponse]:
    """List active members of this organization."""
    return await tenant_service.list_members(db, tenant.tenant_id)


@orgs_router.patch(
    "/{org_id}/members/{member_user_id}",
    response_model=MemberResponse,
    status_code=status.HTTP_200_OK,
    summary="Update member role (owner only)",
)
async def patch_member_role(
    member_user_id: uuid.UUID,
    payload: UpdateMemberRoleRequest,
    tenant: Annotated[TenantContext, Depends(require_org_roles(OrgRole.OWNER))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> MemberResponse:
    """Change a member's role (owner only; protects sole owner)."""
    return await tenant_service.update_member_role(
        db,
        org=tenant.organization,
        actor=tenant.user,
        target_user_id=member_user_id,
        payload=payload,
    )


@orgs_router.delete(
    "/{org_id}/members/{member_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member from organization (owner only)",
)
async def delete_member(
    member_user_id: uuid.UUID,
    tenant: Annotated[TenantContext, Depends(require_org_roles(OrgRole.OWNER))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> Response:
    """Remove a member (owner only; protects sole owner)."""
    await tenant_service.remove_member(
        db,
        org=tenant.organization,
        actor=tenant.user,
        target_user_id=member_user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@orgs_router.post(
    "/{org_id}/leave",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Leave an organization workspace",
)
async def leave_org(
    tenant: Annotated[
        TenantContext,
        Depends(require_org_roles(OrgRole.OWNER, OrgRole.ANALYST, OrgRole.VIEWER)),
    ],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> MessageResponse:
    """Leave an organization (blocked if current user is the sole remaining owner)."""
    await tenant_service.leave_organization(
        db,
        org=tenant.organization,
        membership=tenant.membership,
        actor=tenant.user,
    )
    return MessageResponse(message="Left organization successfully.")


@orgs_router.get(
    "/{org_id}/invitations",
    response_model=list[InvitationResponse],
    status_code=status.HTTP_200_OK,
    summary="List pending invitations (owner only)",
)
async def get_invitations(
    tenant: Annotated[TenantContext, Depends(require_org_roles(OrgRole.OWNER))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> list[InvitationResponse]:
    """List pending unexpired invitations for this organization."""
    return await tenant_service.list_invitations(db, tenant.tenant_id)


@orgs_router.post(
    "/{org_id}/invitations",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a colleague by email (owner only)",
    dependencies=[
        Depends(
            rate_limit(
                "org_invite",
                max_requests=lambda s: s.AUTH_RATE_LIMIT_ORG_INVITE,
                window_seconds=_FIFTEEN_MINUTES,
            )
        )
    ],
)
async def post_invitation(
    payload: CreateInvitationRequest,
    tenant: Annotated[TenantContext, Depends(require_org_roles(OrgRole.OWNER))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
) -> InvitationResponse:
    """Create and email a single-use workspace invitation."""
    return await tenant_service.create_invitation(
        db,
        org=tenant.organization,
        actor=tenant.user,
        payload=payload,
        settings=settings,
        dispatcher=dispatcher,
    )


@orgs_router.delete(
    "/{org_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a pending invitation (owner only)",
)
async def delete_invitation(
    invitation_id: uuid.UUID,
    tenant: Annotated[TenantContext, Depends(require_org_roles(OrgRole.OWNER))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> Response:
    """Revoke a pending organization invitation."""
    await tenant_service.revoke_invitation(
        db,
        org=tenant.organization,
        actor=tenant.user,
        invitation_id=invitation_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@orgs_router.get(
    "/{org_id}/audit-logs",
    response_model=AuditLogListResponse,
    status_code=status.HTTP_200_OK,
    summary="List organization audit logs (owner only)",
)
async def get_audit_logs(
    tenant: Annotated[TenantContext, Depends(require_org_roles(OrgRole.OWNER))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditLogListResponse:
    """Return paginated tenant-isolated audit logs (owner only)."""
    return await tenant_service.list_audit_logs(db, tenant.tenant_id, limit=limit, offset=offset)


@invitations_router.post(
    "/accept",
    response_model=OrganizationSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Accept an organization email invitation",
    dependencies=[
        Depends(
            rate_limit(
                "org_invite_accept",
                max_requests=lambda s: s.AUTH_RATE_LIMIT_VERIFY,
                window_seconds=_FIFTEEN_MINUTES,
            )
        )
    ],
)
async def post_accept_invitation(
    payload: AcceptInvitationRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationSummaryResponse:
    """Accept a pending workspace invitation belonging to the signed-in user's email."""
    return await tenant_service.accept_invitation(db, user=current_user, raw_token=payload.token)
