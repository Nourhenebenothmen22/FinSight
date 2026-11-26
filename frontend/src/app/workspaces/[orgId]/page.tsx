'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/components/auth/AuthProvider';
import { useWorkspace } from '@/components/auth/WorkspaceProvider';
import { LegalDisclaimer } from '@/components/LegalDisclaimer';
import { Navbar } from '@/components/Navbar';
import { extractApiErrorMessage } from '@/lib/api';
import {
  AuditLogEntry,
  InvitableRole,
  OrganizationSummary,
  OrgInvitation,
  OrgMember,
  OrgRole,
  orgsApi,
} from '@/lib/orgs';
import { inviteMemberSchema, updateOrgSchema } from '@/lib/validations/orgs';

const AUDIT_PAGE_SIZE = 20;

function formatInvitationStatus(invitation: OrgInvitation): string {
  if (invitation.accepted_at) {
    return 'Accepted';
  }
  if (invitation.revoked_at) {
    return 'Revoked';
  }
  if (new Date(invitation.expires_at).getTime() <= Date.now()) {
    return 'Expired';
  }
  return 'Pending';
}

export default function WorkspaceDetailPage() {
  const params = useParams<{ orgId: string }>();
  const orgId = typeof params?.orgId === 'string' ? params.orgId : '';
  const router = useRouter();
  const auth = useAuth();
  const workspace = useWorkspace();

  const [org, setOrg] = useState<OrganizationSummary | null>(null);
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [invitations, setInvitations] = useState<OrgInvitation[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditOffset, setAuditOffset] = useState(0);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [renameValue, setRenameValue] = useState('');
  const [renameError, setRenameError] = useState<string | null>(null);
  const [savingRename, setSavingRename] = useState(false);

  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<InvitableRole>('analyst');
  const [inviteEmailError, setInviteEmailError] = useState<string | null>(null);
  const [sendingInvite, setSendingInvite] = useState(false);

  const [busyMemberId, setBusyMemberId] = useState<string | null>(null);
  const [busyInviteId, setBusyInviteId] = useState<string | null>(null);
  const [leavingOrg, setLeavingOrg] = useState(false);

  const renameInputRef = useRef<HTMLInputElement>(null);
  const inviteEmailInputRef = useRef<HTMLInputElement>(null);

  const loadWorkspaceData = useCallback(
    async (offset = 0) => {
      if (!orgId) {
        return;
      }
      setLoading(true);
      setLoadError(null);
      try {
        const [orgData, memberList] = await Promise.all([
          orgsApi.get(orgId),
          orgsApi.listMembers(orgId),
        ]);
        setOrg(orgData);
        setRenameValue(orgData.name);
        setMembers(memberList);

        if (orgData.role === 'owner') {
          const [inviteList, auditPage] = await Promise.all([
            orgsApi.listInvitations(orgId),
            orgsApi.listAuditLogs(orgId, { limit: AUDIT_PAGE_SIZE, offset }),
          ]);
          setInvitations(inviteList);
          setAuditLogs(auditPage.items);
          setAuditTotal(auditPage.total);
          setAuditOffset(auditPage.offset);
        } else {
          setInvitations([]);
          setAuditLogs([]);
          setAuditTotal(0);
        }
      } catch (err) {
        setLoadError(extractApiErrorMessage(err, 'Unable to load workspace details.'));
      } finally {
        setLoading(false);
      }
    },
    [orgId]
  );

  useEffect(() => {
    document.title = org ? `${org.name} — Workspace | FinSight` : 'Workspace | FinSight';
  }, [org]);

  useEffect(() => {
    if (!auth.isLoading && !auth.isAuthenticated) {
      const nextTarget = orgId ? `/workspaces/${encodeURIComponent(orgId)}` : '/workspaces';
      router.replace(`/login?next=${encodeURIComponent(nextTarget)}`);
    }
  }, [auth.isAuthenticated, auth.isLoading, orgId, router]);

  useEffect(() => {
    if (auth.isAuthenticated && orgId) {
      loadWorkspaceData(0);
    }
  }, [auth.isAuthenticated, loadWorkspaceData, orgId]);

  const handleRenameSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!org) {
      return;
    }
    setActionError(null);
    setStatusMessage(null);

    const parsed = updateOrgSchema.safeParse({ name: renameValue });
    if (!parsed.success) {
      setRenameError(parsed.error.issues[0]?.message ?? 'Invalid workspace name.');
      renameInputRef.current?.focus();
      return;
    }

    setRenameError(null);
    setSavingRename(true);
    try {
      const updated = await orgsApi.update(org.id, parsed.data);
      setOrg(updated);
      setRenameValue(updated.name);
      await workspace.reloadWorkspaces();
      setStatusMessage(`Workspace renamed to "${updated.name}".`);
    } catch (err) {
      setActionError(extractApiErrorMessage(err, 'Unable to rename workspace.'));
    } finally {
      setSavingRename(false);
    }
  };

  const handleInviteSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!org) {
      return;
    }
    setActionError(null);
    setStatusMessage(null);

    const parsed = inviteMemberSchema.safeParse({ email: inviteEmail, role: inviteRole });
    if (!parsed.success) {
      setInviteEmailError(parsed.error.issues[0]?.message ?? 'Enter a valid email address.');
      inviteEmailInputRef.current?.focus();
      return;
    }

    setInviteEmailError(null);
    setSendingInvite(true);
    try {
      const created = await orgsApi.createInvitation(org.id, parsed.data);
      setInviteEmail('');
      setStatusMessage(`Invitation sent to ${created.email} as ${created.role}.`);
      await loadWorkspaceData(auditOffset);
    } catch (err) {
      setActionError(extractApiErrorMessage(err, 'Unable to send invitation.'));
    } finally {
      setSendingInvite(false);
    }
  };

  const handleRoleChange = async (member: OrgMember, nextRole: OrgRole) => {
    if (!org || member.role === nextRole) {
      return;
    }
    setActionError(null);
    setStatusMessage(null);
    setBusyMemberId(member.user_id);
    try {
      const updated = await orgsApi.updateMemberRole(org.id, member.user_id, nextRole);
      setMembers((prev) => prev.map((m) => (m.user_id === member.user_id ? updated : m)));
      await workspace.reloadWorkspaces();
      setStatusMessage(`Updated role for ${member.name} to ${updated.role}.`);
      await loadWorkspaceData(auditOffset);
    } catch (err) {
      setActionError(extractApiErrorMessage(err, 'Unable to update member role.'));
    } finally {
      setBusyMemberId(null);
    }
  };

  const handleRemoveMember = async (member: OrgMember) => {
    if (!org) {
      return;
    }
    setActionError(null);
    setStatusMessage(null);
    setBusyMemberId(member.user_id);
    try {
      await orgsApi.removeMember(org.id, member.user_id);
      setMembers((prev) => prev.filter((m) => m.user_id !== member.user_id));
      setStatusMessage(`Removed ${member.name} from ${org.name}.`);
      await loadWorkspaceData(auditOffset);
    } catch (err) {
      setActionError(extractApiErrorMessage(err, 'Unable to remove member.'));
    } finally {
      setBusyMemberId(null);
    }
  };

  const handleRevokeInvitation = async (invitation: OrgInvitation) => {
    if (!org) {
      return;
    }
    setActionError(null);
    setStatusMessage(null);
    setBusyInviteId(invitation.id);
    try {
      await orgsApi.revokeInvitation(org.id, invitation.id);
      setStatusMessage(`Revoked invitation for ${invitation.email}.`);
      await loadWorkspaceData(auditOffset);
    } catch (err) {
      setActionError(extractApiErrorMessage(err, 'Unable to revoke invitation.'));
    } finally {
      setBusyInviteId(null);
    }
  };

  const handleLeaveWorkspace = async () => {
    if (!org) {
      return;
    }
    setActionError(null);
    setStatusMessage(null);
    setLeavingOrg(true);
    try {
      await orgsApi.leave(org.id);
      await workspace.reloadWorkspaces();
      router.push('/workspaces');
    } catch (err) {
      setActionError(extractApiErrorMessage(err, 'Unable to leave workspace.'));
      setLeavingOrg(false);
    }
  };

  const handleAuditPageChange = async (nextOffset: number) => {
    if (!org || nextOffset < 0 || nextOffset >= auditTotal) {
      return;
    }
    try {
      const page = await orgsApi.listAuditLogs(org.id, {
        limit: AUDIT_PAGE_SIZE,
        offset: nextOffset,
      });
      setAuditLogs(page.items);
      setAuditTotal(page.total);
      setAuditOffset(page.offset);
    } catch (err) {
      setActionError(extractApiErrorMessage(err, 'Unable to load audit logs.'));
    }
  };

  if (auth.isLoading || !auth.isAuthenticated) {
    return (
      <div className="min-h-screen bg-surface-50 dark:bg-surface-950">
        <Navbar />
        <main className="mx-auto max-w-5xl px-4 py-12 text-center text-sm text-surface-600 dark:text-surface-400">
          Loading workspace...
        </main>
      </div>
    );
  }

  const isOwner = org?.role === 'owner';
  const isActiveWorkspace = Boolean(org && workspace.activeOrgId === org.id);

  return (
    <div className="min-h-screen bg-surface-50 dark:bg-surface-950">
      <Navbar />

      <main className="mx-auto max-w-5xl space-y-6 px-4 py-10 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <Link
              href="/workspaces"
              className="text-xs font-medium text-primary-700 hover:underline dark:text-primary-400"
            >
              All workspaces
            </Link>
            <div className="mt-1 flex flex-wrap items-center gap-3">
              <h1 className="text-3xl font-bold tracking-tight text-surface-900 dark:text-surface-50">
                {org ? org.name : 'Workspace'}
              </h1>
              {org ? (
                <span className="rounded border border-surface-300 bg-surface-100 px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-surface-700 dark:border-surface-700 dark:bg-surface-800 dark:text-surface-200">
                  {org.role}
                </span>
              ) : null}
            </div>
            {org ? (
              <p className="mt-1 text-xs text-surface-500 dark:text-surface-400">
                Slug: <code className="font-mono">{org.slug}</code>
              </p>
            ) : null}
          </div>

          {org ? (
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={isActiveWorkspace}
                onClick={() => {
                  workspace.setActiveOrgId(org.id);
                  setStatusMessage(`Active workspace set to "${org.name}".`);
                }}
                className="min-h-[40px] rounded-lg border border-surface-300 px-3.5 py-2 text-xs font-semibold text-surface-700 hover:bg-surface-100 disabled:border-primary-600 disabled:bg-primary-50 disabled:text-primary-800 dark:border-surface-700 dark:text-surface-200 dark:hover:bg-surface-800 dark:disabled:border-primary-400 dark:disabled:bg-primary-950/40 dark:disabled:text-primary-200"
              >
                {isActiveWorkspace ? 'Active workspace' : 'Set as active workspace'}
              </button>
              <button
                type="button"
                disabled={leavingOrg}
                onClick={handleLeaveWorkspace}
                className="min-h-[40px] rounded-lg border border-red-300 px-3.5 py-2 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-60 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950/30"
              >
                {leavingOrg ? 'Leaving...' : 'Leave workspace'}
              </button>
            </div>
          ) : null}
        </div>

        <div aria-live="polite" role="status" className="min-h-[1.25rem]">
          {statusMessage ? (
            <div className="rounded-xl border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200">
              {statusMessage}
            </div>
          ) : null}
        </div>

        {loadError || actionError ? (
          <div
            role="alert"
            className="rounded-xl border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200"
          >
            {loadError || actionError}
          </div>
        ) : null}

        {loading ? (
          <section className="rounded-2xl border border-surface-200 bg-white p-6 text-sm text-surface-600 shadow-sm dark:border-surface-800 dark:bg-surface-900 dark:text-surface-400">
            Loading members and workspace settings...
          </section>
        ) : org ? (
          <>
            {/* Owner-only Workspace Settings */}
            {isOwner ? (
              <section className="rounded-2xl border border-surface-200 bg-white p-6 shadow-sm dark:border-surface-800 dark:bg-surface-900">
                <h2
                  id="rename-workspace-heading"
                  className="text-lg font-semibold text-surface-900 dark:text-surface-50"
                >
                  Workspace settings
                </h2>
                <form
                  onSubmit={handleRenameSubmit}
                  aria-labelledby="rename-workspace-heading"
                  noValidate
                  className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-end"
                >
                  <div className="flex-1">
                    <label
                      htmlFor="rename-workspace-name"
                      className="mb-1.5 block text-sm font-medium text-surface-700 dark:text-surface-200"
                    >
                      Workspace name <span aria-hidden="true">*</span>
                    </label>
                    <input
                      ref={renameInputRef}
                      id="rename-workspace-name"
                      name="name"
                      type="text"
                      required
                      maxLength={120}
                      autoComplete="organization"
                      value={renameValue}
                      onChange={(e) => {
                        setRenameValue(e.target.value);
                        if (renameError) {
                          const check = updateOrgSchema.safeParse({ name: e.target.value });
                          setRenameError(
                            check.success ? null : check.error.issues[0]?.message ?? null
                          );
                        }
                      }}
                      aria-invalid={renameError ? 'true' : 'false'}
                      aria-describedby={renameError ? 'rename-workspace-error' : undefined}
                      className="finsight-input min-h-[44px] w-full rounded-lg border border-surface-300 bg-white px-3.5 py-2 text-base text-surface-900 dark:border-surface-700 dark:bg-surface-950 dark:text-surface-50"
                    />
                    {renameError ? (
                      <p
                        id="rename-workspace-error"
                        className="mt-1 text-xs font-medium text-red-700 dark:text-red-300"
                      >
                        {renameError}
                      </p>
                    ) : null}
                  </div>
                  <button
                    type="submit"
                    disabled={savingRename}
                    className="min-h-[44px] rounded-lg bg-primary-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-60"
                  >
                    {savingRename ? 'Saving...' : 'Save name'}
                  </button>
                </form>
              </section>
            ) : null}

            {/* Members Section */}
            <section className="rounded-2xl border border-surface-200 bg-white p-6 shadow-sm dark:border-surface-800 dark:bg-surface-900">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                <h2
                  id="members-heading"
                  className="text-lg font-semibold text-surface-900 dark:text-surface-50"
                >
                  Workspace members
                </h2>
                <span className="text-xs text-surface-500 dark:text-surface-400">
                  {members.length} {members.length === 1 ? 'member' : 'members'}
                </span>
              </div>

              <div
                tabIndex={0}
                role="region"
                aria-labelledby="members-heading"
                className="finsight-table-wrapper rounded-lg border border-surface-200 dark:border-surface-800"
              >
                <table className="finsight-table text-left text-sm">
                  <caption className="visually-hidden">
                    Members belonging to {org.name} and their RBAC roles
                  </caption>
                  <thead className="bg-surface-100 text-xs uppercase tracking-wide text-surface-600 dark:bg-surface-800 dark:text-surface-300">
                    <tr>
                      <th scope="col" className="px-4 py-3 font-semibold">
                        Member
                      </th>
                      <th scope="col" className="px-4 py-3 font-semibold">
                        Email
                      </th>
                      <th scope="col" className="px-4 py-3 font-semibold">
                        Role
                      </th>
                      <th scope="col" className="px-4 py-3 font-semibold">
                        Joined
                      </th>
                      {isOwner ? (
                        <th scope="col" className="px-4 py-3 font-semibold">
                          Actions
                        </th>
                      ) : null}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-200 bg-white dark:divide-surface-800 dark:bg-surface-900">
                    {members.map((member) => {
                      const isSelf = auth.user?.id === member.user_id;
                      const isBusy = busyMemberId === member.user_id;
                      return (
                        <tr key={member.user_id}>
                          <th
                            scope="row"
                            className="whitespace-nowrap px-4 py-3 font-medium text-surface-900 dark:text-surface-50"
                          >
                            {member.name}
                            {isSelf ? (
                              <span className="ml-2 rounded border border-primary-600 bg-primary-50 px-1.5 py-0.5 text-[11px] font-semibold text-primary-800 dark:border-primary-400 dark:bg-primary-950/40 dark:text-primary-200">
                                You
                              </span>
                            ) : null}
                          </th>
                          <td className="px-4 py-3 text-surface-600 dark:text-surface-300">
                            {member.email}
                          </td>
                          <td className="px-4 py-3">
                            {isOwner ? (
                              <>
                                <label
                                  htmlFor={`role-${member.user_id}`}
                                  className="visually-hidden"
                                >
                                  Role for {member.name}
                                </label>
                                <select
                                  id={`role-${member.user_id}`}
                                  value={member.role}
                                  disabled={isBusy}
                                  onChange={(e) =>
                                    handleRoleChange(member, e.target.value as OrgRole)
                                  }
                                  className="min-h-[36px] rounded-lg border border-surface-300 bg-white px-2.5 py-1.5 text-xs font-medium text-surface-900 dark:border-surface-700 dark:bg-surface-950 dark:text-surface-50"
                                >
                                  <option value="owner">owner</option>
                                  <option value="analyst">analyst</option>
                                  <option value="viewer">viewer</option>
                                </select>
                              </>
                            ) : (
                              <span className="rounded border border-surface-300 bg-surface-100 px-2 py-0.5 text-xs font-semibold uppercase text-surface-700 dark:border-surface-700 dark:bg-surface-800 dark:text-surface-200">
                                {member.role}
                              </span>
                            )}
                          </td>
                          <td className="whitespace-nowrap px-4 py-3 text-xs text-surface-500 dark:text-surface-400">
                            {member.accepted_at
                              ? new Date(member.accepted_at).toLocaleDateString()
                              : new Date(member.invited_at).toLocaleDateString()}
                          </td>
                          {isOwner ? (
                            <td className="px-4 py-3">
                              {isSelf ? (
                                <span className="text-xs text-surface-400">Current account</span>
                              ) : (
                                <button
                                  type="button"
                                  disabled={isBusy}
                                  aria-label={`Remove ${member.name}`}
                                  onClick={() => handleRemoveMember(member)}
                                  className="min-h-[36px] rounded-lg border border-red-300 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-60 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950/30"
                                >
                                  Remove
                                </button>
                              )}
                            </td>
                          ) : null}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Owner-only Invite & Pending Invitations */}
            {isOwner ? (
              <section className="rounded-2xl border border-surface-200 bg-white p-6 shadow-sm dark:border-surface-800 dark:bg-surface-900">
                <h2
                  id="invite-heading"
                  className="text-lg font-semibold text-surface-900 dark:text-surface-50"
                >
                  Invite team members
                </h2>
                <p className="mt-1 text-xs text-surface-500 dark:text-surface-400">
                  Colleagues receive a signed invitation link and join once authenticated with the
                  invited email address.
                </p>

                <form
                  onSubmit={handleInviteSubmit}
                  aria-labelledby="invite-heading"
                  noValidate
                  className="mt-4 space-y-4"
                >
                  <div>
                    <label
                      htmlFor="invite-email"
                      className="mb-1.5 block text-sm font-medium text-surface-700 dark:text-surface-200"
                    >
                      Colleague email <span aria-hidden="true">*</span>
                    </label>
                    <input
                      ref={inviteEmailInputRef}
                      id="invite-email"
                      name="email"
                      type="email"
                      required
                      autoComplete="email"
                      autoCapitalize="none"
                      autoCorrect="off"
                      spellCheck={false}
                      enterKeyHint="next"
                      value={inviteEmail}
                      onChange={(e) => {
                        setInviteEmail(e.target.value);
                        if (inviteEmailError) {
                          const check = inviteMemberSchema.safeParse({
                            email: e.target.value,
                            role: inviteRole,
                          });
                          setInviteEmailError(
                            check.success ? null : check.error.issues[0]?.message ?? null
                          );
                        }
                      }}
                      aria-invalid={inviteEmailError ? 'true' : 'false'}
                      aria-describedby={inviteEmailError ? 'invite-email-error' : undefined}
                      placeholder="colleague@company.com"
                      className="finsight-input min-h-[44px] w-full rounded-lg border border-surface-300 bg-white px-3.5 py-2 text-base text-surface-900 sm:max-w-md dark:border-surface-700 dark:bg-surface-950 dark:text-surface-50"
                    />
                    {inviteEmailError ? (
                      <p
                        id="invite-email-error"
                        className="mt-1 text-xs font-medium text-red-700 dark:text-red-300"
                      >
                        {inviteEmailError}
                      </p>
                    ) : null}
                  </div>

                  <fieldset className="space-y-2">
                    <legend className="text-sm font-medium text-surface-700 dark:text-surface-200">
                      Assigned role
                    </legend>
                    <div className="flex flex-wrap gap-4">
                      <label
                        htmlFor="invite-role-analyst"
                        className="flex min-h-[44px] cursor-pointer items-center gap-2 rounded-lg border border-surface-300 px-3.5 py-2 text-sm text-surface-800 dark:border-surface-700 dark:text-surface-200"
                      >
                        <input
                          id="invite-role-analyst"
                          type="radio"
                          name="invite_role"
                          value="analyst"
                          checked={inviteRole === 'analyst'}
                          onChange={() => setInviteRole('analyst')}
                          className="h-4 w-4 accent-primary-600"
                        />
                        <span>
                          <strong>Analyst</strong> — can run & view analyses
                        </span>
                      </label>
                      <label
                        htmlFor="invite-role-viewer"
                        className="flex min-h-[44px] cursor-pointer items-center gap-2 rounded-lg border border-surface-300 px-3.5 py-2 text-sm text-surface-800 dark:border-surface-700 dark:text-surface-200"
                      >
                        <input
                          id="invite-role-viewer"
                          type="radio"
                          name="invite_role"
                          value="viewer"
                          checked={inviteRole === 'viewer'}
                          onChange={() => setInviteRole('viewer')}
                          className="h-4 w-4 accent-primary-600"
                        />
                        <span>
                          <strong>Viewer</strong> — read-only workspace access
                        </span>
                      </label>
                    </div>
                  </fieldset>

                  <button
                    type="submit"
                    disabled={sendingInvite}
                    className="min-h-[44px] rounded-lg bg-primary-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-60"
                  >
                    {sendingInvite ? 'Sending...' : 'Send invitation'}
                  </button>
                </form>

                <div className="mt-8">
                  <h3
                    id="invitations-heading"
                    className="mb-3 text-sm font-semibold text-surface-800 dark:text-surface-200"
                  >
                    Invitations ({invitations.length})
                  </h3>

                  {invitations.length === 0 ? (
                    <p className="text-xs text-surface-500 dark:text-surface-400">
                      No invitations sent for this workspace yet.
                    </p>
                  ) : (
                    <div
                      tabIndex={0}
                      role="region"
                      aria-labelledby="invitations-heading"
                      className="finsight-table-wrapper rounded-lg border border-surface-200 dark:border-surface-800"
                    >
                      <table className="finsight-table text-left text-sm">
                        <caption className="visually-hidden">
                          Workspace invitations for {org.name}
                        </caption>
                        <thead className="bg-surface-100 text-xs uppercase tracking-wide text-surface-600 dark:bg-surface-800 dark:text-surface-300">
                          <tr>
                            <th scope="col" className="px-4 py-3 font-semibold">
                              Invitee email
                            </th>
                            <th scope="col" className="px-4 py-3 font-semibold">
                              Role
                            </th>
                            <th scope="col" className="px-4 py-3 font-semibold">
                              Status
                            </th>
                            <th scope="col" className="px-4 py-3 font-semibold">
                              Expires
                            </th>
                            <th scope="col" className="px-4 py-3 font-semibold">
                              Action
                            </th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-surface-200 bg-white dark:divide-surface-800 dark:bg-surface-900">
                          {invitations.map((inv) => {
                            const statusLabel = formatInvitationStatus(inv);
                            const isPending = statusLabel === 'Pending';
                            return (
                              <tr key={inv.id}>
                                <th
                                  scope="row"
                                  className="px-4 py-3 font-medium text-surface-900 dark:text-surface-50"
                                >
                                  {inv.email}
                                </th>
                                <td className="px-4 py-3 text-xs uppercase text-surface-700 dark:text-surface-300">
                                  {inv.role}
                                </td>
                                <td className="px-4 py-3 text-xs text-surface-700 dark:text-surface-300">
                                  {statusLabel}
                                </td>
                                <td className="whitespace-nowrap px-4 py-3 text-xs text-surface-500 dark:text-surface-400">
                                  {new Date(inv.expires_at).toLocaleDateString()}
                                </td>
                                <td className="px-4 py-3">
                                  {isPending ? (
                                    <button
                                      type="button"
                                      disabled={busyInviteId === inv.id}
                                      aria-label={`Revoke invitation for ${inv.email}`}
                                      onClick={() => handleRevokeInvitation(inv)}
                                      className="min-h-[36px] rounded-lg border border-surface-300 px-3 py-1.5 text-xs font-medium text-surface-700 hover:bg-surface-100 disabled:opacity-60 dark:border-surface-700 dark:text-surface-200 dark:hover:bg-surface-800"
                                    >
                                      Revoke
                                    </button>
                                  ) : (
                                    <span className="text-xs text-surface-400">—</span>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </section>
            ) : null}

            {/* Owner-only Audit Logs */}
            {isOwner ? (
              <section className="rounded-2xl border border-surface-200 bg-white p-6 shadow-sm dark:border-surface-800 dark:bg-surface-900">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h2
                      id="audit-heading"
                      className="text-lg font-semibold text-surface-900 dark:text-surface-50"
                    >
                      Workspace audit log
                    </h2>
                    <p className="text-xs text-surface-500 dark:text-surface-400">
                      Server-recorded tenant governance events ({auditTotal} total).
                    </p>
                  </div>
                  {auditTotal > AUDIT_PAGE_SIZE ? (
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        disabled={auditOffset === 0}
                        onClick={() =>
                          handleAuditPageChange(Math.max(0, auditOffset - AUDIT_PAGE_SIZE))
                        }
                        className="min-h-[36px] rounded-lg border border-surface-300 px-3 py-1.5 text-xs font-medium text-surface-700 hover:bg-surface-100 disabled:opacity-50 dark:border-surface-700 dark:text-surface-200 dark:hover:bg-surface-800"
                      >
                        Previous
                      </button>
                      <button
                        type="button"
                        disabled={auditOffset + AUDIT_PAGE_SIZE >= auditTotal}
                        onClick={() => handleAuditPageChange(auditOffset + AUDIT_PAGE_SIZE)}
                        className="min-h-[36px] rounded-lg border border-surface-300 px-3 py-1.5 text-xs font-medium text-surface-700 hover:bg-surface-100 disabled:opacity-50 dark:border-surface-700 dark:text-surface-200 dark:hover:bg-surface-800"
                      >
                        Next
                      </button>
                    </div>
                  ) : null}
                </div>

                {auditLogs.length === 0 ? (
                  <p className="text-xs text-surface-500 dark:text-surface-400">
                    No audit events recorded yet.
                  </p>
                ) : (
                  <div
                    tabIndex={0}
                    role="region"
                    aria-labelledby="audit-heading"
                    className="finsight-table-wrapper rounded-lg border border-surface-200 dark:border-surface-800"
                  >
                    <table className="finsight-table text-left text-xs">
                      <caption className="visually-hidden">
                        Tenant audit log events for {org.name}
                      </caption>
                      <thead className="bg-surface-100 uppercase tracking-wide text-surface-600 dark:bg-surface-800 dark:text-surface-300">
                        <tr>
                          <th scope="col" className="px-4 py-3 font-semibold">
                            Action
                          </th>
                          <th scope="col" className="px-4 py-3 font-semibold">
                            Target
                          </th>
                          <th scope="col" className="px-4 py-3 font-semibold">
                            Details
                          </th>
                          <th scope="col" className="px-4 py-3 font-semibold">
                            Timestamp
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-surface-200 bg-white dark:divide-surface-800 dark:bg-surface-900">
                        {auditLogs.map((entry) => (
                          <tr key={entry.id}>
                            <th
                              scope="row"
                              className="whitespace-nowrap px-4 py-3 font-mono font-semibold text-surface-900 dark:text-surface-100"
                            >
                              {entry.action}
                            </th>
                            <td className="px-4 py-3 font-mono text-surface-600 dark:text-surface-300">
                              {entry.target}
                            </td>
                            <td className="px-4 py-3 font-mono text-surface-600 dark:text-surface-400">
                              {Object.keys(entry.metadata).length > 0
                                ? JSON.stringify(entry.metadata)
                                : '—'}
                            </td>
                            <td className="whitespace-nowrap px-4 py-3 text-surface-500 dark:text-surface-400">
                              {new Date(entry.created_at).toLocaleString()}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            ) : null}
          </>
        ) : null}

        <LegalDisclaimer />
      </main>
    </div>
  );
}
