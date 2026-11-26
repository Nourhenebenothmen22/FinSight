"""Pydantic schemas for multi-tenant organizations, memberships, invitations, and audit logs (F2)."""

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from app.models.tenant import OrgRole

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def _normalize_org_name(value: str) -> str:
    """Trim whitespace and strip control characters from workspace names."""
    cleaned = _CONTROL_CHARS_RE.sub("", value).strip()
    if not cleaned:
        raise ValueError("Organization name must not be empty")
    return cleaned


def _normalize_email(value: EmailStr) -> str:
    """Normalize invitee email consistently to trimmed lowercase."""
    return str(value).strip().lower()


CleanOrgName = Annotated[
    str, Field(min_length=1, max_length=120), AfterValidator(_normalize_org_name)
]
NormalizedEmail = Annotated[EmailStr, AfterValidator(_normalize_email)]


class CreateOrganizationRequest(BaseModel):
    """Create a new tenant workspace."""

    name: CleanOrgName


class UpdateOrganizationRequest(BaseModel):
    """Update workspace details."""

    name: CleanOrgName


class OrganizationSummaryResponse(BaseModel):
    """Organization summary enriched with the current user's RBAC role."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    owner_id: uuid.UUID
    plan_id: uuid.UUID | None
    role: OrgRole
    created_at: datetime


class MemberResponse(BaseModel):
    """Organization member projection joined with user profile."""

    user_id: uuid.UUID
    email: str
    name: str
    role: OrgRole
    invited_at: datetime
    accepted_at: datetime | None


class UpdateMemberRoleRequest(BaseModel):
    """Change a member's RBAC role."""

    role: OrgRole


class CreateInvitationRequest(BaseModel):
    """Invite a colleague by email as analyst or viewer."""

    email: NormalizedEmail
    role: Literal[OrgRole.ANALYST, OrgRole.VIEWER] = OrgRole.ANALYST


class InvitationResponse(BaseModel):
    """Organization email invitation record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    email: str
    role: OrgRole
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class AcceptInvitationRequest(BaseModel):
    """Accept an email invitation token."""

    token: str = Field(min_length=16, max_length=512)


class AuditLogResponse(BaseModel):
    """Tenant audit log entry."""

    id: uuid.UUID
    org_id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    target: str
    metadata: dict[str, Any]
    created_at: datetime


class AuditLogListResponse(BaseModel):
    """Paginated tenant audit log response."""

    items: list[AuditLogResponse]
    total: int
    limit: int
    offset: int
