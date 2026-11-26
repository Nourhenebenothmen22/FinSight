'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { FormEvent, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/components/auth/AuthProvider';
import { useWorkspace } from '@/components/auth/WorkspaceProvider';
import { LegalDisclaimer } from '@/components/LegalDisclaimer';
import { Navbar } from '@/components/Navbar';
import { extractApiErrorMessage } from '@/lib/api';
import { orgsApi } from '@/lib/orgs';
import { createOrgSchema } from '@/lib/validations/orgs';

export default function WorkspacesPage() {
  const router = useRouter();
  const auth = useAuth();
  const workspace = useWorkspace();

  const [name, setName] = useState('');
  const [nameError, setNameError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  const nameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    document.title = 'Workspaces | FinSight';
  }, []);

  useEffect(() => {
    if (!auth.isLoading && !auth.isAuthenticated) {
      router.replace('/login?next=%2Fworkspaces');
    }
  }, [auth.isAuthenticated, auth.isLoading, router]);

  const validateName = (value: string): boolean => {
    const parsed = createOrgSchema.safeParse({ name: value });
    if (parsed.success) {
      setNameError(null);
      return true;
    }
    setNameError(parsed.error.issues[0]?.message ?? 'Invalid workspace name.');
    return false;
  };

  const handleCreateWorkspace = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setServerError(null);
    setStatusMessage(null);

    const parsed = createOrgSchema.safeParse({ name });
    if (!parsed.success) {
      setNameError(parsed.error.issues[0]?.message ?? 'Invalid workspace name.');
      nameInputRef.current?.focus();
      return;
    }

    setNameError(null);
    setIsCreating(true);
    try {
      const created = await orgsApi.create(parsed.data);
      setName('');
      await workspace.reloadWorkspaces();
      workspace.setActiveOrgId(created.id);
      setStatusMessage(`Created and switched to "${created.name}".`);
    } catch (err) {
      setServerError(extractApiErrorMessage(err, 'Unable to create workspace.'));
    } finally {
      setIsCreating(false);
    }
  };

  const handleSwitchWorkspace = (orgId: string, orgName: string) => {
    workspace.setActiveOrgId(orgId);
    setServerError(null);
    setStatusMessage(`Active workspace switched to "${orgName}".`);
  };

  if (auth.isLoading || !auth.isAuthenticated) {
    return (
      <div className="min-h-screen bg-surface-50 dark:bg-surface-950">
        <Navbar />
        <main className="mx-auto max-w-4xl px-4 py-12 text-center text-sm text-surface-600 dark:text-surface-400">
          Loading workspaces...
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-surface-50 dark:bg-surface-950">
      <Navbar />

      <main className="mx-auto max-w-4xl space-y-6 px-4 py-10 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-surface-900 dark:text-surface-50">
              Workspaces
            </h1>
            <p className="mt-1 text-sm text-surface-600 dark:text-surface-400">
              Switch tenant context, create team workspaces, and manage role-based access (`owner`,
              `analyst`, `viewer`).
            </p>
          </div>
          <Link
            href="/profile"
            className="inline-flex min-h-[40px] items-center rounded-lg border border-surface-300 px-3.5 py-2 text-sm font-medium text-surface-700 hover:bg-surface-100 dark:border-surface-700 dark:text-surface-200 dark:hover:bg-surface-800"
          >
            Back to profile
          </Link>
        </div>

        {/* Centralized polite live status announcements & critical error alerts */}
        <div aria-live="polite" role="status" className="min-h-[1.25rem]">
          {statusMessage ? (
            <div className="rounded-xl border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200">
              {statusMessage}
            </div>
          ) : null}
        </div>

        {serverError || workspace.error ? (
          <div
            role="alert"
            className="rounded-xl border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200"
          >
            {serverError || workspace.error}
          </div>
        ) : null}

        {/* Create Workspace Form */}
        <section className="rounded-2xl border border-surface-200 bg-white p-6 shadow-sm dark:border-surface-800 dark:bg-surface-900">
          <h2
            id="create-workspace-heading"
            className="text-lg font-semibold text-surface-900 dark:text-surface-50"
          >
            Create a workspace
          </h2>
          <p className="mt-1 text-xs text-surface-500 dark:text-surface-400">
            Start a new isolated tenant workspace where you are assigned the owner role.
          </p>

          <form
            onSubmit={handleCreateWorkspace}
            aria-labelledby="create-workspace-heading"
            noValidate
            className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-end"
          >
            <div className="flex-1">
              <label
                htmlFor="workspace-name"
                className="mb-1.5 block text-sm font-medium text-surface-700 dark:text-surface-200"
              >
                Workspace name <span aria-hidden="true">*</span>
              </label>
              <input
                ref={nameInputRef}
                id="workspace-name"
                name="name"
                type="text"
                required
                maxLength={120}
                autoComplete="organization"
                enterKeyHint="done"
                value={name}
                onChange={(e) => {
                  const val = e.target.value;
                  setName(val);
                  if (nameError) {
                    validateName(val);
                  }
                }}
                onBlur={(e) => {
                  if (e.target.value.length > 0) {
                    validateName(e.target.value);
                  }
                }}
                aria-invalid={nameError ? 'true' : 'false'}
                aria-describedby={nameError ? 'workspace-name-error' : 'workspace-name-hint'}
                placeholder="Acme Capital Research"
                className="finsight-input min-h-[44px] w-full rounded-lg border border-surface-300 bg-white px-3.5 py-2 text-base text-surface-900 dark:border-surface-700 dark:bg-surface-950 dark:text-surface-50"
              />
              <p
                id="workspace-name-hint"
                className="mt-1 text-xs text-surface-500 dark:text-surface-400"
              >
                Up to 120 characters. A unique URL slug is generated automatically.
              </p>
              {nameError ? (
                <p
                  id="workspace-name-error"
                  className="mt-1 text-xs font-medium text-red-700 dark:text-red-300"
                >
                  {nameError}
                </p>
              ) : null}
            </div>

            <button
              type="submit"
              disabled={isCreating}
              className="min-h-[44px] rounded-lg bg-primary-600 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-700 disabled:opacity-60"
            >
              {isCreating ? 'Creating...' : 'Create workspace'}
            </button>
          </form>
        </section>

        {/* Workspace List */}
        <section className="rounded-2xl border border-surface-200 bg-white p-6 shadow-sm dark:border-surface-800 dark:bg-surface-900">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-semibold text-surface-900 dark:text-surface-50">
              Your workspaces
            </h2>
            <span className="text-xs text-surface-500 dark:text-surface-400">
              {workspace.workspaces.length}{' '}
              {workspace.workspaces.length === 1 ? 'workspace' : 'workspaces'}
            </span>
          </div>

          {workspace.isLoading ? (
            <p className="text-sm text-surface-500 dark:text-surface-400">Loading workspaces...</p>
          ) : workspace.workspaces.length === 0 ? (
            <p className="text-sm text-surface-500 dark:text-surface-400">
              No workspaces found for this account yet. Create one above or accept an invitation.
            </p>
          ) : (
            <ul className="divide-y divide-surface-200 dark:divide-surface-800">
              {workspace.workspaces.map((org) => {
                const isActive = workspace.activeOrgId === org.id;
                return (
                  <li
                    key={org.id}
                    className="flex flex-wrap items-center justify-between gap-4 py-4 first:pt-1 last:pb-1"
                  >
                    <div className="min-w-0 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-base font-semibold text-surface-900 dark:text-surface-50">
                          {org.name}
                        </h3>
                        <span className="rounded border border-surface-300 bg-surface-100 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-surface-700 dark:border-surface-700 dark:bg-surface-800 dark:text-surface-200">
                          {org.role}
                        </span>
                        {isActive ? (
                          <span className="rounded border border-primary-600 bg-primary-50 px-2 py-0.5 text-xs font-semibold text-primary-800 dark:border-primary-400 dark:bg-primary-950/50 dark:text-primary-200">
                            Active workspace
                          </span>
                        ) : null}
                      </div>
                      <p className="text-xs text-surface-500 dark:text-surface-400">
                        Slug: <code className="font-mono">{org.slug}</code> • Created{' '}
                        {new Date(org.created_at).toLocaleDateString()}
                      </p>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleSwitchWorkspace(org.id, org.name)}
                        aria-pressed={isActive}
                        aria-label={
                          isActive ? `Active workspace: ${org.name}` : `Use workspace ${org.name}`
                        }
                        disabled={isActive}
                        className={`min-h-[40px] rounded-lg border px-3.5 py-2 text-xs font-semibold transition-colors ${
                          isActive
                            ? 'cursor-default border-primary-600 bg-primary-50 text-primary-800 dark:border-primary-400 dark:bg-primary-950/40 dark:text-primary-200'
                            : 'border-surface-300 text-surface-700 hover:bg-surface-100 dark:border-surface-700 dark:text-surface-200 dark:hover:bg-surface-800'
                        }`}
                      >
                        {isActive ? 'Active workspace' : 'Use workspace'}
                      </button>

                      <Link
                        href={`/workspaces/${org.id}`}
                        aria-label={`Manage ${org.name}`}
                        className="inline-flex min-h-[40px] items-center rounded-lg bg-surface-900 px-3.5 py-2 text-xs font-semibold text-white transition-colors hover:bg-surface-800 dark:bg-surface-100 dark:text-surface-900 dark:hover:bg-surface-200"
                      >
                        Manage
                      </Link>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <LegalDisclaimer />
      </main>
    </div>
  );
}
