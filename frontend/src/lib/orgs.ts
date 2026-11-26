/** Organization workspace, membership, invitation, and audit log API helpers (F2). */

import { api } from '@/lib/api';

export type OrgRole = 'owner' | 'analyst' | 'viewer';
export type InvitableRole = 'analyst' | 'viewer';

export interface OrganizationSummary {
  id: string;
  name: string;
  slug: string;
  owner_id: string;
  plan_id: string | null;
  role: OrgRole;
  created_at: string;
}

export interface OrgMember {
  user_id: string;
  email: string;
  name: string;
  role: OrgRole;
  invited_at: string;
  accepted_at: string | null;
}

export interface OrgInvitation {
  id: string;
  org_id: string;
  email: string;
  role: OrgRole;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface AuditLogEntry {
  id: string;
  org_id: string;
  actor_id: string | null;
  action: string;
  target: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface AuditLogListResponse {
  items: AuditLogEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface OrgMessageResponse {
  message: string;
}

export const orgsApi = {
  list: () => api.get<OrganizationSummary[]>('/api/v1/orgs'),
  create: (payload: { name: string }) => api.post<OrganizationSummary>('/api/v1/orgs', payload),
  get: (orgId: string) => api.get<OrganizationSummary>(`/api/v1/orgs/${encodeURIComponent(orgId)}`),
  update: (orgId: string, payload: { name: string }) =>
    api.patch<OrganizationSummary>(`/api/v1/orgs/${encodeURIComponent(orgId)}`, payload),
  listMembers: (orgId: string) =>
    api.get<OrgMember[]>(`/api/v1/orgs/${encodeURIComponent(orgId)}/members`),
  updateMemberRole: (orgId: string, userId: string, role: OrgRole) =>
    api.patch<OrgMember>(
      `/api/v1/orgs/${encodeURIComponent(orgId)}/members/${encodeURIComponent(userId)}`,
      { role }
    ),
  removeMember: (orgId: string, userId: string) =>
    api.delete<void>(
      `/api/v1/orgs/${encodeURIComponent(orgId)}/members/${encodeURIComponent(userId)}`
    ),
  leave: (orgId: string) =>
    api.post<OrgMessageResponse>(`/api/v1/orgs/${encodeURIComponent(orgId)}/leave`),
  listInvitations: (orgId: string) =>
    api.get<OrgInvitation[]>(`/api/v1/orgs/${encodeURIComponent(orgId)}/invitations`),
  createInvitation: (orgId: string, payload: { email: string; role: InvitableRole }) =>
    api.post<OrgInvitation>(`/api/v1/orgs/${encodeURIComponent(orgId)}/invitations`, payload),
  revokeInvitation: (orgId: string, invitationId: string) =>
    api.delete<void>(
      `/api/v1/orgs/${encodeURIComponent(orgId)}/invitations/${encodeURIComponent(invitationId)}`
    ),
  listAuditLogs: (orgId: string, params: { limit?: number; offset?: number } = {}) => {
    const query = new URLSearchParams();
    if (params.limit !== undefined) {
      query.set('limit', String(params.limit));
    }
    if (params.offset !== undefined) {
      query.set('offset', String(params.offset));
    }
    const qs = query.toString();
    return api.get<AuditLogListResponse>(
      `/api/v1/orgs/${encodeURIComponent(orgId)}/audit-logs${qs ? `?${qs}` : ''}`
    );
  },
  acceptInvitation: (token: string) =>
    api.post<OrganizationSummary>('/api/v1/invitations/accept', { token }),
};
