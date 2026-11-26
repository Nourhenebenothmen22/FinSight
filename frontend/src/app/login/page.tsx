'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { FormEvent, Suspense, useMemo, useRef, useState } from 'react';
import { AuthCard } from '@/components/auth/AuthCard';
import { useAuth } from '@/components/auth/AuthProvider';
import { GoogleOAuthButton } from '@/components/auth/GoogleOAuthButton';
import { PasswordInput } from '@/components/auth/PasswordInput';
import { ApiError, extractApiErrorMessage } from '@/lib/api';
import { authApi, sanitizeNextPath } from '@/lib/auth';
import { loginSchema } from '@/lib/validations/auth';

const OAUTH_ERROR_MESSAGES: Record<string, string> = {
  oauth_denied: 'Google sign-in was cancelled.',
  invalid_state: 'Your sign-in session expired. Please try Google sign-in again.',
  oauth_unavailable: 'Google OAuth is not configured on this environment.',
  email_unverified_conflict:
    'An unverified email/password account exists with this address. Please verify your email first before linking Google.',
  oauth_subject_mismatch: 'This email is already linked to a different Google account.',
  account_inactive: 'This account has been deactivated.',
  oauth_failed: 'Google authentication failed. Please try again.',
};

function LoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const auth = useAuth();

  const nextPath = useMemo(
    () => sanitizeNextPath(searchParams.get('next'), '/profile'),
    [searchParams]
  );
  const oauthErrorCode = searchParams.get('oauth_error');
  const oauthErrorMessage = oauthErrorCode
    ? OAUTH_ERROR_MESSAGES[oauthErrorCode] || OAUTH_ERROR_MESSAGES.oauth_failed
    : null;

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});
  const [serverError, setServerError] = useState<string | null>(oauthErrorMessage);
  const [needsVerification, setNeedsVerification] = useState(false);
  const [resendStatus, setResendStatus] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const validateField = (field: 'email' | 'password', nextVal?: string) => {
    const candidate = {
      email: field === 'email' ? nextVal ?? email : email,
      password: field === 'password' ? nextVal ?? password : password,
    };
    const parsed = loginSchema.safeParse(candidate);
    if (parsed.success) {
      setFieldErrors((prev) => ({ ...prev, [field]: undefined }));
      return;
    }
    const issue = parsed.error.issues.find((item) => item.path[0] === field);
    setFieldErrors((prev) => ({ ...prev, [field]: issue?.message }));
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setServerError(null);
    setNeedsVerification(false);
    setResendStatus(null);

    const parsed = loginSchema.safeParse({ email, password });
    if (!parsed.success) {
      const nextErrors: { email?: string; password?: string } = {};
      for (const issue of parsed.error.issues) {
        const key = issue.path[0];
        if ((key === 'email' || key === 'password') && !nextErrors[key]) {
          nextErrors[key] = issue.message;
        }
      }
      setFieldErrors(nextErrors);
      if (nextErrors.email) emailRef.current?.focus();
      else if (nextErrors.password) passwordRef.current?.focus();
      return;
    }

    setFieldErrors({});
    setIsSubmitting(true);
    try {
      const tokens = await authApi.login(parsed.data);
      auth.setSession(tokens);
      router.push(nextPath);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        const msg = extractApiErrorMessage(err);
        if (msg.toLowerCase().includes('verified')) {
          setNeedsVerification(true);
        }
      }
      setServerError(extractApiErrorMessage(err, 'Invalid email or password.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResendVerification = async () => {
    setResendStatus(null);
    const parsedEmail = loginSchema.shape.email.safeParse(email);
    if (!parsedEmail.success) {
      setResendStatus('Please enter your email address first.');
      return;
    }
    try {
      const res = await authApi.resendVerification(parsedEmail.data);
      setResendStatus(res.message);
    } catch (err) {
      setResendStatus(extractApiErrorMessage(err, 'Unable to resend verification email.'));
    }
  };

  return (
    <AuthCard title="Sign in to FinSight" subtitle="Access your financial analysis workspace.">
      <div className="space-y-5">
        <GoogleOAuthButton nextPath={nextPath} />

        <div className="relative">
          <div className="absolute inset-0 flex items-center" aria-hidden="true">
            <div className="w-full border-t border-surface-200 dark:border-surface-800" />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-white px-2 text-surface-500 dark:bg-surface-900 dark:text-surface-400">
              Or sign in with email
            </span>
          </div>
        </div>

        {serverError ? (
          <div
            role="alert"
            className="space-y-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200"
          >
            <p>{serverError}</p>
            {needsVerification ? (
              <button
                type="button"
                onClick={handleResendVerification}
                className="font-medium underline hover:no-underline"
              >
                Resend verification email
              </button>
            ) : null}
            {resendStatus ? (
              <p className="text-xs text-surface-700 dark:text-surface-200">{resendStatus}</p>
            ) : null}
          </div>
        ) : null}

        <form onSubmit={handleSubmit} method="post" noValidate className="space-y-4">
          <div className="space-y-1.5">
            <label
              htmlFor="login-email"
              className="block text-sm font-medium text-surface-800 dark:text-surface-200"
            >
              Email address
              <span className="ml-1 text-red-600" aria-hidden="true">
                *
              </span>
            </label>
            <input
              ref={emailRef}
              id="login-email"
              name="email"
              type="email"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                if (fieldErrors.email) validateField('email', event.target.value);
              }}
              onBlur={() => validateField('email')}
              autoComplete="username"
              spellCheck={false}
              autoCapitalize="none"
              autoCorrect="off"
              enterKeyHint="next"
              required
              aria-invalid={fieldErrors.email ? 'true' : 'false'}
              aria-describedby={fieldErrors.email ? 'login-email-error' : undefined}
              className={`finsight-input min-h-[48px] w-full rounded-lg border px-3.5 py-2.5 text-base text-surface-900 shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 dark:bg-surface-950 dark:text-surface-50 ${
                fieldErrors.email
                  ? 'border-red-600 bg-red-50/50 dark:border-red-500'
                  : 'border-surface-300 bg-white dark:border-surface-700'
              }`}
            />
            {fieldErrors.email ? (
              <p
                id="login-email-error"
                className="flex items-start gap-1.5 text-sm text-red-700 dark:text-red-300"
              >
                <span role="img" aria-label="Error">
                  !
                </span>
                <span>{fieldErrors.email}</span>
              </p>
            ) : null}
          </div>

          <PasswordInput
            id="login-password"
            name="password"
            label="Password"
            value={password}
            onChange={(val) => {
              setPassword(val);
              if (fieldErrors.password) validateField('password', val);
            }}
            onBlur={() => validateField('password')}
            autoComplete="current-password"
            enterKeyHint="done"
            inputRef={passwordRef}
            error={fieldErrors.password}
          />

          <div className="flex justify-end">
            <Link
              href="/forgot-password"
              className="text-sm font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400"
            >
              Forgot password?
            </Link>
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="min-h-[48px] w-full rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        <p className="text-center text-sm text-surface-600 dark:text-surface-400">
          New to FinSight?{' '}
          <Link
            href="/register"
            className="font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400"
          >
            Create an account
          </Link>
        </p>
      </div>
    </AuthCard>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginContent />
    </Suspense>
  );
}
