'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { FormEvent, Suspense, useEffect, useRef, useState } from 'react';
import { AuthCard } from '@/components/auth/AuthCard';
import { extractApiErrorMessage } from '@/lib/api';
import { authApi } from '@/lib/auth';

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const initialToken = searchParams.get('token') ?? '';

  const [token, setToken] = useState(initialToken);
  const [status, setStatus] = useState<'idle' | 'verifying' | 'verified' | 'error'>(
    initialToken ? 'verifying' : 'idle'
  );
  const [message, setMessage] = useState<string | null>(null);
  const attemptedRef = useRef(false);

  useEffect(() => {
    if (!initialToken || attemptedRef.current) {
      return;
    }
    attemptedRef.current = true;
    authApi
      .verifyEmail(initialToken)
      .then((res) => {
        setStatus('verified');
        setMessage(res.message);
      })
      .catch((err) => {
        setStatus('error');
        setMessage(extractApiErrorMessage(err, 'Verification link is invalid or expired.'));
      });
  }, [initialToken]);

  const handleManualSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const cleaned = token.trim();
    if (!cleaned) {
      setStatus('error');
      setMessage('Please enter a verification token.');
      return;
    }
    setStatus('verifying');
    setMessage(null);
    try {
      const res = await authApi.verifyEmail(cleaned);
      setStatus('verified');
      setMessage(res.message);
    } catch (err) {
      setStatus('error');
      setMessage(extractApiErrorMessage(err, 'Verification token is invalid or expired.'));
    }
  };

  return (
    <AuthCard title="Email verification" subtitle="Confirm your FinSight account email address.">
      {status === 'verifying' ? (
        <div
          role="status"
          className="py-6 text-center text-sm text-surface-600 dark:text-surface-300"
        >
          Verifying your email address...
        </div>
      ) : null}

      {status === 'verified' ? (
        <div role="status" className="space-y-4">
          <p className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-800 dark:border-green-900 dark:bg-green-950/30 dark:text-green-200">
            {message || 'Your email address has been verified.'}
          </p>
          <Link
            href="/login"
            className="flex min-h-[48px] w-full items-center justify-center rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary-700"
          >
            Continue to sign in
          </Link>
        </div>
      ) : null}

      {status === 'idle' || status === 'error' ? (
        <div className="space-y-4">
          {status === 'error' && message ? (
            <div
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200"
            >
              {message}
            </div>
          ) : null}

          <form onSubmit={handleManualSubmit} method="post" className="space-y-4">
            <div className="space-y-1.5">
              <label
                htmlFor="verify-token"
                className="block text-sm font-medium text-surface-800 dark:text-surface-200"
              >
                Verification token
              </label>
              <input
                id="verify-token"
                name="token"
                type="text"
                value={token}
                onChange={(event) => setToken(event.target.value)}
                required
                spellCheck={false}
                autoCapitalize="none"
                autoCorrect="off"
                className="min-h-[48px] w-full rounded-lg border border-surface-300 bg-white px-3.5 py-2.5 text-base text-surface-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 dark:border-surface-700 dark:bg-surface-950 dark:text-surface-50"
              />
            </div>

            <button
              type="submit"
              className="min-h-[48px] w-full rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary-700"
            >
              Verify email
            </button>
          </form>
        </div>
      ) : null}
    </AuthCard>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailContent />
    </Suspense>
  );
}
