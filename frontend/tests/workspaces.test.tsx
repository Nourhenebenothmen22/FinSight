/** Component and integration tests for F2 WorkspaceProvider, workspace pages, RBAC views, and invitations. */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import * as nextNavigation from 'next/navigation';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AcceptInvitationPage from '@/app/invitations/accept/page';
import WorkspaceDetailPage from '@/app/workspaces/[orgId]/page';
import WorkspacesPage from '@/app/workspaces/page';
import { AuthProvider } from '@/components/auth/AuthProvider';
import { WorkspaceProvider } from '@/components/auth/WorkspaceProvider';
import { api, ApiError } from '@/lib/api';
import { authApi, AuthUser, TokenResponse } from '@/lib/auth';
import {
  AuditLogListResponse,
  OrganizationSummary,
  OrgInvitation,
  OrgMember,
  orgsApi,
} from '@/lib/orgs';
import { createOrgSchema, inviteMemberSchema } from '@/lib/validations/orgs';

const aliceUser: AuthUser = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'alice@example.com',
  name: 'Alice Owner',
  email_verified_at: '2026-11-26T12:00:00Z',
  oauth_provider: null,
  has_password: true,
  is_active: true,
  last_login_at: '2026-11-26T13:00:00Z',
  created_at: '2026-11-26T10:00:00Z',
};

const aliceTokens: TokenResponse = {
  access_token: 'alice-access-token',
  token_type: 'bearer',
  expires_in: 1800,
  user: aliceUser,
};

const personalOrg: OrganizationSummary = {
  id: '11111111-1111-1111-1111-111111111111',
  name: "Alice Owner's Workspace",
  slug: 'alice-owners-workspace',
  owner_id: aliceUser.id,
  plan_id: null,
  role: 'owner',
  created_at: '2026-11-26T10:00:00Z',
};

const teamOrg: OrganizationSummary = {
  id: '22222222-2222-2222-2222-222222222222',
  name: 'Alpha Research',
  slug: 'alpha-research',
  owner_id: '00000000-0000-0000-0000-000000000099',
  plan_id: null,
  role: 'analyst',
  created_at: '2026-11-26T11:00:00Z',
};

describe('F2 Workspace Validation Schemas', () => {
  it('validates workspace names and colleague invite emails cleanly', () => {
    expect(createOrgSchema.safeParse({ name: '   ' }).success).toBe(false);
    const okOrg = createOrgSchema.safeParse({ name: '  Acme Capital  ' });
    expect(okOrg.success).toBe(true);
    if (okOrg.success) {
      expect(okOrg.data.name).toBe('Acme Capital');
    }

    expect(inviteMemberSchema.safeParse({ email: 'not-an-email', role: 'analyst' }).success).toBe(
      false
    );
    expect(inviteMemberSchema.safeParse({ email: 'bob@example.com', role: 'owner' }).success).toBe(
      false
    );
    const okInvite = inviteMemberSchema.safeParse({
      email: '  Bob@Example.COM ',
      role: 'viewer',
    });
    expect(okInvite.success).toBe(true);
    if (okInvite.success) {
      expect(okInvite.data.email).toBe('bob@example.com');
      expect(okInvite.data.role).toBe('viewer');
    }
  });
});

describe('F2 Workspaces & Tenant RBAC UI', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    vi
      .mocked(nextNavigation.useSearchParams)
      .mockImplementation?.(() => new URLSearchParams() as never);
    vi.mocked(nextNavigation.useParams).mockImplementation?.(() => ({}) as never);
  });

  it('WorkspaceProvider attaches active X-Tenant-ID header to API requests', async () => {
    vi.spyOn(authApi, 'refresh').mockResolvedValue(aliceTokens);
    vi.spyOn(orgsApi, 'list').mockResolvedValue([personalOrg, teamOrg]);

    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <AuthProvider>
        <WorkspaceProvider>
          <WorkspacesPage />
        </WorkspaceProvider>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Alpha Research')).toBeInTheDocument();
    });

    await api.get('/api/v1/orgs');
    expect(fetchMock).toHaveBeenCalled();
    const lastCall = fetchMock.mock.calls.at(-1);
    const sentHeaders = lastCall?.[1]?.headers as Headers;
    expect(sentHeaders.get('x-tenant-id')).toBe(personalOrg.id);

    fireEvent.click(screen.getByRole('button', { name: 'Use workspace Alpha Research' }));
    await waitFor(() => {
      expect(
        screen.getByText(/Active workspace switched to "Alpha Research"/i)
      ).toBeInTheDocument();
    });

    await api.get('/api/v1/orgs');
    const switchedCall = fetchMock.mock.calls.at(-1);
    expect((switchedCall?.[1]?.headers as Headers).get('x-tenant-id')).toBe(teamOrg.id);
  });

  it('WorkspacesPage validates input and creates a new workspace', async () => {
    vi.spyOn(authApi, 'refresh').mockResolvedValue(aliceTokens);
    const createdOrg: OrganizationSummary = {
      id: '33333333-3333-3333-3333-333333333333',
      name: 'Nordic Equities',
      slug: 'nordic-equities',
      owner_id: aliceUser.id,
      plan_id: null,
      role: 'owner',
      created_at: '2026-11-26T12:00:00Z',
    };
    const listSpy = vi
      .spyOn(orgsApi, 'list')
      .mockResolvedValueOnce([personalOrg])
      .mockResolvedValueOnce([personalOrg, createdOrg]);
    const createSpy = vi.spyOn(orgsApi, 'create').mockResolvedValue(createdOrg);

    render(
      <AuthProvider>
        <WorkspaceProvider>
          <WorkspacesPage />
        </WorkspaceProvider>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: "Alice Owner's Workspace" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Create workspace/i }));
    expect(screen.getByText(/Please enter a workspace name/i)).toBeInTheDocument();
    expect(createSpy).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(/Workspace name/i), {
      target: { value: 'Nordic Equities' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Create workspace/i }));

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith({ name: 'Nordic Equities' });
      expect(listSpy).toHaveBeenCalledTimes(2);
      expect(screen.getByText(/Created and switched to "Nordic Equities"/i)).toBeInTheDocument();
    });
  });

  it('WorkspaceDetailPage renders owner management, invitations, audit logs, and disclaimer', async () => {
    vi.spyOn(nextNavigation, 'useParams').mockReturnValue({ orgId: personalOrg.id });
    vi.spyOn(authApi, 'refresh').mockResolvedValue(aliceTokens);
    vi.spyOn(orgsApi, 'list').mockResolvedValue([personalOrg]);
    vi.spyOn(orgsApi, 'get').mockResolvedValue(personalOrg);

    const members: OrgMember[] = [
      {
        user_id: aliceUser.id,
        email: aliceUser.email,
        name: aliceUser.name,
        role: 'owner',
        invited_at: '2026-11-26T10:00:00Z',
        accepted_at: '2026-11-26T10:00:00Z',
      },
      {
        user_id: '00000000-0000-0000-0000-000000000002',
        email: 'bob@example.com',
        name: 'Bob Analyst',
        role: 'analyst',
        invited_at: '2026-11-26T11:00:00Z',
        accepted_at: '2026-11-26T11:05:00Z',
      },
    ];
    const invitations: OrgInvitation[] = [
      {
        id: '44444444-4444-4444-4444-444444444444',
        org_id: personalOrg.id,
        email: 'carol@example.com',
        role: 'viewer',
        expires_at: '2099-12-03T10:00:00Z',
        accepted_at: null,
        revoked_at: null,
        created_at: '2026-11-26T11:00:00Z',
      },
    ];
    const auditPage: AuditLogListResponse = {
      items: [
        {
          id: '55555555-5555-5555-5555-555555555555',
          org_id: personalOrg.id,
          actor_id: aliceUser.id,
          action: 'org.created',
          target: `organization:${personalOrg.id}`,
          metadata: { slug: personalOrg.slug },
          created_at: '2026-11-26T10:00:00Z',
        },
      ],
      total: 1,
      limit: 20,
      offset: 0,
    };

    vi.spyOn(orgsApi, 'listMembers').mockResolvedValue(members);
    vi.spyOn(orgsApi, 'listInvitations').mockResolvedValue(invitations);
    vi.spyOn(orgsApi, 'listAuditLogs').mockResolvedValue(auditPage);
    const inviteSpy = vi.spyOn(orgsApi, 'createInvitation').mockResolvedValue({
      id: '66666666-6666-6666-6666-666666666666',
      org_id: personalOrg.id,
      email: 'dave@example.com',
      role: 'viewer',
      expires_at: '2099-12-03T10:00:00Z',
      accepted_at: null,
      revoked_at: null,
      created_at: '2026-11-26T12:00:00Z',
    });
    const revokeInviteSpy = vi.spyOn(orgsApi, 'revokeInvitation').mockResolvedValue(undefined);
    const roleSpy = vi.spyOn(orgsApi, 'updateMemberRole').mockResolvedValue({
      ...members[1],
      role: 'viewer',
    });

    render(
      <AuthProvider>
        <WorkspaceProvider>
          <WorkspaceDetailPage />
        </WorkspaceProvider>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Workspace members')).toBeInTheDocument();
    });

    expect(screen.getByText('Bob Analyst')).toBeInTheDocument();
    expect(screen.getByText('carol@example.com')).toBeInTheDocument();
    expect(screen.getByText('org.created')).toBeInTheDocument();
    expect(screen.getByText(/not investment advice/i)).toBeInTheDocument();

    // Update member role
    fireEvent.change(screen.getByLabelText('Role for Bob Analyst'), {
      target: { value: 'viewer' },
    });
    await waitFor(() => {
      expect(roleSpy).toHaveBeenCalledWith(personalOrg.id, members[1].user_id, 'viewer');
    });

    // Send invitation
    fireEvent.change(screen.getByLabelText(/Colleague email/i), {
      target: { value: 'dave@example.com' },
    });
    fireEvent.click(screen.getByLabelText(/Viewer/i));
    fireEvent.click(screen.getByRole('button', { name: /Send invitation/i }));
    await waitFor(() => {
      expect(inviteSpy).toHaveBeenCalledWith(personalOrg.id, {
        email: 'dave@example.com',
        role: 'viewer',
      });
    });

    // Revoke pending invitation
    fireEvent.click(
      screen.getByRole('button', { name: 'Revoke invitation for carol@example.com' })
    );
    await waitFor(() => {
      expect(revokeInviteSpy).toHaveBeenCalledWith(personalOrg.id, invitations[0].id);
    });
  });

  it('WorkspaceDetailPage hides owner-only panels for non-owner analyst role', async () => {
    vi.spyOn(nextNavigation, 'useParams').mockReturnValue({ orgId: teamOrg.id });
    vi.spyOn(authApi, 'refresh').mockResolvedValue(aliceTokens);
    vi.spyOn(orgsApi, 'list').mockResolvedValue([teamOrg]);
    vi.spyOn(orgsApi, 'get').mockResolvedValue(teamOrg);
    vi.spyOn(orgsApi, 'listMembers').mockResolvedValue([
      {
        user_id: aliceUser.id,
        email: aliceUser.email,
        name: aliceUser.name,
        role: 'analyst',
        invited_at: '2026-11-26T11:00:00Z',
        accepted_at: '2026-11-26T11:00:00Z',
      },
    ]);
    const listInvitesSpy = vi.spyOn(orgsApi, 'listInvitations');
    const listAuditSpy = vi.spyOn(orgsApi, 'listAuditLogs');

    render(
      <AuthProvider>
        <WorkspaceProvider>
          <WorkspaceDetailPage />
        </WorkspaceProvider>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Workspace members')).toBeInTheDocument();
    });

    expect(listInvitesSpy).not.toHaveBeenCalled();
    expect(listAuditSpy).not.toHaveBeenCalled();
    expect(screen.queryByText('Workspace settings')).not.toBeInTheDocument();
    expect(screen.queryByText('Invite team members')).not.toBeInTheDocument();
    expect(screen.queryByText('Workspace audit log')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Leave workspace/i })).toBeInTheDocument();
  });

  it('AcceptInvitationPage prompts unauthenticated users with safe next redirect and accepts when signed in', async () => {
    const tokenValue = 'invite-token-1234567890abcdef';
    vi.spyOn(nextNavigation, 'useSearchParams').mockReturnValue(
      new URLSearchParams(`token=${tokenValue}`) as never
    );

    // 1. Unauthenticated branch
    vi.spyOn(authApi, 'refresh').mockRejectedValueOnce(
      new ApiError('Unauthorized', 401, { detail: 'No session' })
    );

    const { unmount } = render(
      <AuthProvider>
        <WorkspaceProvider>
          <AcceptInvitationPage />
        </WorkspaceProvider>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByRole('link', { name: /Sign in to accept/i })).toBeInTheDocument();
    });

    const expectedNext = encodeURIComponent(`/invitations/accept?token=${tokenValue}`);
    expect(screen.getByRole('link', { name: /Sign in to accept/i })).toHaveAttribute(
      'href',
      `/login?next=${expectedNext}`
    );
    unmount();

    // 2. Authenticated auto-accept branch
    vi.spyOn(authApi, 'refresh').mockResolvedValue(aliceTokens);
    vi.spyOn(orgsApi, 'list').mockResolvedValue([personalOrg, teamOrg]);
    const acceptSpy = vi.spyOn(orgsApi, 'acceptInvitation').mockResolvedValue(teamOrg);

    render(
      <AuthProvider>
        <WorkspaceProvider>
          <AcceptInvitationPage />
        </WorkspaceProvider>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(acceptSpy).toHaveBeenCalledWith(tokenValue);
      expect(screen.getByText(/You joined/i)).toBeInTheDocument();
      expect(screen.getByRole('link', { name: /Open workspace/i })).toHaveAttribute(
        'href',
        `/workspaces/${teamOrg.id}`
      );
    });
  });
});
