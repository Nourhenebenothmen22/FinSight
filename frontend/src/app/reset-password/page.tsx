'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { FormEvent, Suspense, useRef, useState } from 'react';
import { AuthCard } from '@/components/auth/AuthCard';
import { PasswordInput } from '@/components/auth/PasswordInput';
import { PasswordRulesList } from '@/components/auth/PasswordRulesList';
import { extractApiErrorMessage } from '@/lib/api';
import { authApi } from '@/lib/auth';
import { resetPasswordSchema } from '@/lib/validations/auth';

function ResetPasswordContent() {
  const searchParams = useSearchParams();
  const [token, setToken] = useState(searchParams.get('token') ?? '');
  const [newPassword, setNewPassword] = useState('');
  const [touchedPassword, setTouchedPassword] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<{ token?: string; new_password?: string }>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [completedMessage, setCompletedMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const tokenRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setServerError(null);
    setTouchedPassword(true);

    const parsed = resetPasswordSchema.safeParse({ token, new_password: newPassword });
    if (!parsed.success) {
      const nextErrors: { token?: string; new_password?: string } = {};
      for (const issue of parsed.error.issues) {
        const key = issue.path[0];
        if ((key === 'token' || key === 'new_password') && !nextErrors[key]) {
          nextErrors[key] = issue.message;
        }
      }
      setFieldErrors(nextErrors);
      if (nextErrors.token) tokenRef.current?.focus();
      else if (nextErrors.new_password) passwordRef.current?.focus();
      return;
    }

    setFieldErrors({});
    setIsSubmitting(true);
    try {
      const res = await authApi.resetPassword(parsed.data);
      setCompletedMessage(res.message);
    } catch (err) {
      setServerError(extractApiErrorMessage(err, 'Password reset failed.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AuthCard
      title="Choose a new password"
      subtitle="Enter a strong new password for your account."
    >
      {completedMessage ? (
        <div role="status" className="space-y-4">
          <p className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-800 dark:border-green-900 dark:bg-green-950/30 dark:text-green-200">
            {completedMessage}
          </p>
          <Link
            href="/login"
            className="flex min-h-[48px] w-full items-center justify-center rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary-700"
          >
            Sign in with new password
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
            {!searchParams.get('token') ? (
              <div className="space-y-1.5">
                <label
                  htmlFor="reset-token"
                  className="block text-sm font-medium text-surface-800 dark:text-surface-200"
                >
                  Reset token
                </label>
                <input
                  ref={tokenRef}
                  id="reset-token"
                  name="token"
                  type="text"
                  value={token}
                  onChange={(event) => setToken(event.target.value)}
                  required
                  spellCheck={false}
                  autoCapitalize="none"
                  autoCorrect="off"
                  aria-invalid={fieldErrors.token ? 'true' : 'false'}
                  className="min-h-[48px] w-full rounded-lg border border-surface-300 bg-white px-3.5 py-2.5 text-base text-surface-900 dark:border-surface-700 dark:bg-surface-950 dark:text-surface-50"
                />
                {fieldErrors.token ? (
                  <p className="text-sm text-red-700 dark:text-red-300">{fieldErrors.token}</p>
                ) : null}
              </div>
            ) : null}

            <PasswordInput
              id="reset-password"
              name="new_password"
              label="New password"
              value={newPassword}
              onChange={(val) => {
                setNewPassword(val);
                if (fieldErrors.new_password) {
                  const res = resetPasswordSchema.shape.new_password.safeParse(val);
                  setFieldErrors((prev) => ({
                    ...prev,
                    new_password: res.success ? undefined : res.error.issues[0]?.message,
                  }));
                }
              }}
              onBlur={() => {
                setTouchedPassword(true);
                const res = resetPasswordSchema.shape.new_password.safeParse(newPassword);
                setFieldErrors((prev) => ({
                  ...prev,
                  new_password: res.success ? undefined : res.error.issues[0]?.message,
                }));
              }}
              autoComplete="new-password"
              minLength={12}
              enterKeyHint="done"
              inputRef={passwordRef}
              hintId="reset-password-rules"
              hintAbove={
                <PasswordRulesList
                  id="reset-password-rules"
                  password={newPassword}
                  showStatus={Boolean(touchedPassword || newPassword.length > 0)}
                />
              }
              error={fieldErrors.new_password}
            />

            <button
              type="submit"
              disabled={isSubmitting}
              className="min-h-[48px] w-full rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-60"
            >
              {isSubmitting ? 'Updating password...' : 'Update password'}
            </button>
          </form>
        </div>
      )}
    </AuthCard>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordContent />
    </Suspense>
  );
}
