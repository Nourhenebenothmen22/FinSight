'use client';

import Link from 'next/link';
import { FormEvent, useRef, useState } from 'react';
import { AuthCard } from '@/components/auth/AuthCard';
import { extractApiErrorMessage } from '@/lib/api';
import { authApi } from '@/lib/auth';
import { forgotPasswordSchema } from '@/lib/validations/auth';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [submittedMessage, setSubmittedMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const emailRef = useRef<HTMLInputElement>(null);

  const validateEmail = (value: string) => {
    const parsed = forgotPasswordSchema.safeParse({ email: value });
    setFieldError(parsed.success ? null : parsed.error.issues[0]?.message ?? 'Invalid email.');
    return parsed;
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setServerError(null);
    const parsed = validateEmail(email);
    if (!parsed.success) {
      emailRef.current?.focus();
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await authApi.forgotPassword(parsed.data.email);
      setSubmittedMessage(response.message);
    } catch (err) {
      setServerError(extractApiErrorMessage(err, 'Unable to submit password reset request.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AuthCard
      title="Reset your password"
      subtitle="Enter your account email and we will send a single-use reset link."
    >
      {submittedMessage ? (
        <div role="status" className="space-y-4">
          <p className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-800 dark:border-green-900 dark:bg-green-950/30 dark:text-green-200">
            {submittedMessage}
          </p>
          <Link
            href="/login"
            className="flex min-h-[48px] w-full items-center justify-center rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary-700"
          >
            Back to sign in
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          {serverError ? (
            <div
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200"
            >
              {serverError}
            </div>
          ) : null}

          <form onSubmit={handleSubmit} method="post" noValidate className="space-y-4">
            <div className="space-y-1.5">
              <label
                htmlFor="forgot-email"
                className="block text-sm font-medium text-surface-800 dark:text-surface-200"
              >
                Email address
                <span className="ml-1 text-red-600" aria-hidden="true">
                  *
                </span>
              </label>
              <input
                ref={emailRef}
                id="forgot-email"
                name="email"
                type="email"
                value={email}
                onChange={(event) => {
                  setEmail(event.target.value);
                  if (fieldError) validateEmail(event.target.value);
                }}
                onBlur={() => validateEmail(email)}
                autoComplete="username"
                spellCheck={false}
                autoCapitalize="none"
                autoCorrect="off"
                required
                aria-invalid={fieldError ? 'true' : 'false'}
                aria-describedby={fieldError ? 'forgot-email-error' : undefined}
                className={`finsight-input min-h-[48px] w-full rounded-lg border px-3.5 py-2.5 text-base text-surface-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 dark:bg-surface-950 dark:text-surface-50 ${
                  fieldError
                    ? 'border-red-600 bg-red-50/50 dark:border-red-500'
                    : 'border-surface-300 bg-white dark:border-surface-700'
                }`}
              />
              {fieldError ? (
                <p
                  id="forgot-email-error"
                  className="flex items-start gap-1.5 text-sm text-red-700 dark:text-red-300"
                >
                  <span role="img" aria-label="Error">
                    !
                  </span>
                  <span>{fieldError}</span>
                </p>
              ) : null}
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="min-h-[48px] w-full rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-60"
            >
              {isSubmitting ? 'Sending reset link...' : 'Send reset link'}
            </button>
          </form>

          <p className="text-center text-sm text-surface-600 dark:text-surface-400">
            Remembered your password?{' '}
            <Link
              href="/login"
              className="font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400"
            >
              Sign in
            </Link>
          </p>
        </div>
      )}
    </AuthCard>
  );
}
