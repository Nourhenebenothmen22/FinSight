'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useRef, useState } from 'react';
import { AuthCard } from '@/components/auth/AuthCard';
import { useAuth } from '@/components/auth/AuthProvider';
import { extractApiErrorMessage } from '@/lib/api';
import { authApi, sanitizeNextPath } from '@/lib/auth';

function GoogleCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const auth = useAuth();
  const code = searchParams.get('code');

  const [error, setError] = useState<string | null>(
    code ? null : 'Missing Google authentication exchange code.'
  );
  const attemptedRef = useRef(false);

  useEffect(() => {
    if (!code || attemptedRef.current) {
      return;
    }
    attemptedRef.current = true;
    authApi
      .exchangeGoogleCode(code)
      .then((tokens) => {
        auth.setSession(tokens);
        router.replace(sanitizeNextPath(tokens.next_path, '/profile'));
      })
      .catch((err) => {
        setError(extractApiErrorMessage(err, 'Google sign-in could not be completed.'));
      });
  }, [auth, code, router]);

  return (
    <AuthCard title="Completing sign in" subtitle="Finishing your Google sign-in with FinSight.">
      {error ? (
        <div role="alert" className="space-y-4">
          <p className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200">
            {error}
          </p>
          <Link
            href="/login"
            className="flex min-h-[48px] w-full items-center justify-center rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary-700"
          >
            Return to sign in
          </Link>
        </div>
      ) : (
        <div
          role="status"
          className="py-8 text-center text-sm text-surface-600 dark:text-surface-300"
        >
          Verifying your Google account session...
        </div>
      )}
    </AuthCard>
  );
}

export default function GoogleCallbackPage() {
  return (
    <Suspense fallback={null}>
      <GoogleCallbackContent />
    </Suspense>
  );
}
