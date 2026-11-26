'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useOptionalAuth } from '@/components/auth/AuthProvider';

export function Navbar() {
  const auth = useOptionalAuth();
  const router = useRouter();

  const handleLogout = async () => {
    if (!auth) {
      return;
    }
    await auth.logout();
    router.push('/login');
  };

  return (
    <header className="border-b border-surface-200 bg-white/90 backdrop-blur dark:border-surface-800 dark:bg-surface-900/90">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3 sm:px-6 lg:px-8">
        <Link
          href="/"
          className="text-lg font-bold tracking-tight text-surface-900 hover:text-primary-600 dark:text-surface-50 dark:hover:text-primary-400"
        >
          FinSight
        </Link>

        <nav aria-label="Main navigation" className="flex items-center gap-3">
          {auth?.isAuthenticated && auth.user ? (
            <>
              <Link
                href="/profile"
                className="rounded-lg px-3 py-2 text-sm font-medium text-surface-700 transition-colors hover:bg-surface-100 dark:text-surface-200 dark:hover:bg-surface-800"
              >
                {auth.user.name}
              </Link>
              <button
                type="button"
                onClick={handleLogout}
                className="rounded-lg border border-surface-300 px-3 py-2 text-sm font-medium text-surface-700 transition-colors hover:bg-surface-100 dark:border-surface-600 dark:text-surface-200 dark:hover:bg-surface-800"
              >
                Sign out
              </button>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className="rounded-lg px-3 py-2 text-sm font-medium text-surface-700 transition-colors hover:bg-surface-100 dark:text-surface-200 dark:hover:bg-surface-800"
              >
                Sign in
              </Link>
              <Link
                href="/register"
                className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-700"
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
