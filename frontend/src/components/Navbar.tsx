'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useOptionalAuth } from '@/components/auth/AuthProvider';
import { useOptionalWorkspace } from '@/components/auth/WorkspaceProvider';

export function Navbar() {
  const auth = useOptionalAuth();
  const workspace = useOptionalWorkspace();
  const pathname = usePathname();
  const router = useRouter();

  const handleLogout = async () => {
    if (!auth) {
      return;
    }
    await auth.logout();
    router.push('/login');
  };

  const isWorkspacesRoute = Boolean(pathname?.startsWith('/workspaces'));
  const isProfileRoute = pathname === '/profile';

  return (
    <header className="border-b border-surface-200 bg-white/90 backdrop-blur dark:border-surface-800 dark:bg-surface-900/90">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-8">
        <Link
          href="/"
          className="text-lg font-bold tracking-tight text-surface-900 hover:text-primary-600 dark:text-surface-50 dark:hover:text-primary-400"
        >
          FinSight
        </Link>

        <nav aria-label="Primary" className="flex flex-wrap items-center gap-2 sm:gap-3">
          {auth?.isAuthenticated && auth.user ? (
            <>
              <Link
                href="/workspaces"
                aria-current={isWorkspacesRoute ? 'page' : undefined}
                className={`inline-flex min-h-[40px] items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isWorkspacesRoute
                    ? 'border border-primary-600 bg-primary-50 text-primary-800 underline decoration-2 underline-offset-4 dark:border-primary-400 dark:bg-primary-950/40 dark:text-primary-200'
                    : 'text-surface-700 hover:bg-surface-100 dark:text-surface-200 dark:hover:bg-surface-800'
                }`}
              >
                <span>{workspace?.activeWorkspace?.name ?? 'Workspaces'}</span>
                {workspace?.activeWorkspace ? (
                  <span className="rounded border border-surface-300 bg-surface-100 px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-surface-700 dark:border-surface-600 dark:bg-surface-800 dark:text-surface-200">
                    {workspace.activeWorkspace.role}
                  </span>
                ) : null}
              </Link>
              <Link
                href="/profile"
                aria-current={isProfileRoute ? 'page' : undefined}
                className={`inline-flex min-h-[40px] items-center rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isProfileRoute
                    ? 'border border-primary-600 bg-primary-50 text-primary-800 underline decoration-2 underline-offset-4 dark:border-primary-400 dark:bg-primary-950/40 dark:text-primary-200'
                    : 'text-surface-700 hover:bg-surface-100 dark:text-surface-200 dark:hover:bg-surface-800'
                }`}
              >
                {auth.user.name}
              </Link>
              <button
                type="button"
                onClick={handleLogout}
                className="min-h-[40px] rounded-lg border border-surface-300 px-3 py-2 text-sm font-medium text-surface-700 transition-colors hover:bg-surface-100 dark:border-surface-600 dark:text-surface-200 dark:hover:bg-surface-800"
              >
                Sign out
              </button>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className="inline-flex min-h-[40px] items-center rounded-lg px-3 py-2 text-sm font-medium text-surface-700 transition-colors hover:bg-surface-100 dark:text-surface-200 dark:hover:bg-surface-800"
              >
                Sign in
              </Link>
              <Link
                href="/register"
                className="inline-flex min-h-[40px] items-center rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-700"
              >
                Create account
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
