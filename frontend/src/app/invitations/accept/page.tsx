'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { FormEvent, Suspense, useEffect, useRef, useState } from 'react';
import { AuthCard } from '@/components/auth/AuthCard';
import { useAuth } from '@/components/auth/AuthProvider';
import { useOptionalWorkspace } from '@/components/auth/WorkspaceProvider';
import { extractApiErrorMessage } from '@/lib/api';
import { OrganizationSummary, orgsApi } from '@/lib/orgs';
import { acceptInvitationSchema } from '@/lib/validations/orgs';

function AcceptInvitationContent() {
  const searchParams = useSearchParams();
  const auth = useAuth();
  const workspace = useOptionalWorkspace();

  const initialToken = searchParams.get('token') ?? '';
  const [token, setToken] = useState(initialToken);
  const [status, setStatus] = useState<'idle' | 'accepting' | 'accepted' | 'error'>('idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [acceptedOrg, setAcceptedOrg] = useState<OrganizationSummary | null>(null);
  const attemptedAutoRef = useRef(false);

  const acceptPath = initialToken
    ? `/invitations/accept?token=${encodeURIComponent(initialToken)}`
    : '/invitations/accept';
  const encodedNext = encodeURIComponent(acceptPath);

  useEffect(() => {
    document.title = 'Accept Workspace Invitation | FinSight';
  }, []);

  useEffect(() => {
    if (auth.isLoading || !auth.isAuthenticated || !initialToken || attemptedAutoRef.current) {
      return;
    }

    const parsed = acceptInvitationSchema.safeParse({ token: initialToken });
    if (!parsed.success) {
      setStatus('error');
      setErrorMessage(parsed.error.issues[0]?.message ?? 'Invalid invitation link.');
      return;
    }

    attemptedAutoRef.current = true;
    setStatus('accepting');
    setErrorMessage(null);

    orgsApi
      .acceptInvitation(parsed.data.token)
      .then(async (org) => {
        setAcceptedOrg(org);
        setStatus('accepted');
        if (workspace) {
          await workspace.reloadWorkspaces();
          workspace.setActiveOrgId(org.id);
        }
      })
      .catch((err) => {
        setStatus('error');
        setErrorMessage(extractApiErrorMessage(err, 'Unable to accept this workspace invitation.'));
      });
  }, [auth.isAuthenticated, auth.isLoading, initialToken, workspace]);

  const handleManualSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage(null);

    const parsed = acceptInvitationSchema.safeParse({ token });
    if (!parsed.success) {
      setStatus('error');
      setErrorMessage(parsed.error.issues[0]?.message ?? 'Please enter a valid invitation token.');
      return;
    }

    setStatus('accepting');
    try {
      const org = await orgsApi.acceptInvitation(parsed.data.token);
      setAcceptedOrg(org);
      setStatus('accepted');
      if (workspace) {
        await workspace.reloadWorkspaces();
        workspace.setActiveOrgId(org.id);
      }
    } catch (err) {
      setStatus('error');
      setErrorMessage(extractApiErrorMessage(err, 'Unable to accept this workspace invitation.'));
    }
  };

  if (auth.isLoading) {
    return (
      <AuthCard
        title="Workspace invitation"
        subtitle="Checking your FinSight authentication state..."
      >
        <p className="text-sm text-surface-600 dark:text-surface-300">Loading session...</p>
      </AuthCard>
    );
  }

  if (!auth.isAuthenticated) {
    return (
      <AuthCard
        title="Workspace invitation"
        subtitle="Sign in or create an account with the invited email address to accept."
      >
        <div className="space-y-4">
          <p className="text-sm text-surface-700 dark:text-surface-300">
            For security, workspace invitations can only be accepted by the matching authenticated
            FinSight email address.
          </p>
          <div className="flex flex-col gap-2.5 sm:flex-row">
            <Link
              href={`/login?next=${encodedNext}`}
              className="inline-flex min-h-[44px] flex-1 items-center justify-center rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary-700"
            >
              Sign in to accept
            </Link>
            <Link
              href={`/register?next=${encodedNext}`}
              className="inline-flex min-h-[44px] flex-1 items-center justify-center rounded-lg border border-surface-300 px-4 py-2.5 text-sm font-semibold text-surface-700 hover:bg-surface-100 dark:border-surface-700 dark:text-surface-200 dark:hover:bg-surface-800"
            >
              Create account
            </Link>
          </div>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Workspace invitation"
      subtitle={`Signed in as ${auth.user?.email ?? 'your account'}`}
    >
      {status === 'accepting' ? (
        <p role="status" className="text-sm text-surface-700 dark:text-surface-300">
          Accepting workspace invitation...
        </p>
      ) : null}

      {status === 'accepted' && acceptedOrg ? (
        <div className="space-y-4">
          <div
            role="status"
            className="rounded-xl border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200"
          >
            You joined <strong>{acceptedOrg.name}</strong> with the{' '}
            <strong>{acceptedOrg.role}</strong> role.
          </div>
          <div className="flex flex-col gap-2.5 sm:flex-row">
            <Link
              href={`/workspaces/${acceptedOrg.id}`}
              className="inline-flex min-h-[44px] flex-1 items-center justify-center rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary-700"
            >
              Open workspace
            </Link>
            <Link
              href="/workspaces"
              className="inline-flex min-h-[44px] flex-1 items-center justify-center rounded-lg border border-surface-300 px-4 py-2.5 text-sm font-semibold text-surface-700 hover:bg-surface-100 dark:border-surface-700 dark:text-surface-200 dark:hover:bg-surface-800"
            >
              View all workspaces
            </Link>
          </div>
        </div>
      ) : null}

      {status !== 'accepted' && status !== 'accepting' ? (
        <form onSubmit={handleManualSubmit} noValidate className="space-y-4">
          {errorMessage ? (
            <div
              role="alert"
              className="rounded-xl border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200"
            >
              {errorMessage}
            </div>
          ) : null}

          <div>
            <label
              htmlFor="invitation-token"
              className="mb-1.5 block text-sm font-medium text-surface-700 dark:text-surface-200"
            >
              Invitation token <span aria-hidden="true">*</span>
            </label>
            <input
              id="invitation-token"
              name="token"
              type="text"
              required
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              value={token}
              onChange={(e) => setToken(e.target.value)}
              aria-invalid={errorMessage ? 'true' : 'false'}
              placeholder="Paste token from invitation email"
              className="finsight-input min-h-[44px] w-full rounded-lg border border-surface-300 bg-white px-3.5 py-2 font-mono text-sm text-surface-900 dark:border-surface-700 dark:bg-surface-950 dark:text-surface-50"
            />
          </div>

          <button
            type="submit"
            className="min-h-[44px] w-full rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary-700"
          >
            Accept invitation
          </button>
        </form>
      ) : null}
    </AuthCard>
  );
}

export default function AcceptInvitationPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-surface-50 px-4 py-12 text-center text-sm text-surface-500 dark:bg-surface-950">
          Loading invitation...
        </div>
      }
    >
      <AcceptInvitationContent />
    </Suspense>
  );
}
