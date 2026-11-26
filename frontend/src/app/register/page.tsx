'use client';

import Link from 'next/link';
import { FormEvent, useRef, useState } from 'react';
import { AuthCard } from '@/components/auth/AuthCard';
import { GoogleOAuthButton } from '@/components/auth/GoogleOAuthButton';
import { PasswordInput } from '@/components/auth/PasswordInput';
import { PasswordRulesList } from '@/components/auth/PasswordRulesList';
import { extractApiErrorMessage } from '@/lib/api';
import { authApi } from '@/lib/auth';
import { registerSchema } from '@/lib/validations/auth';

export default function RegisterPage() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [touched, setTouched] = useState<{ name?: boolean; email?: boolean; password?: boolean }>(
    {}
  );
  const [fieldErrors, setFieldErrors] = useState<{
    name?: string;
    email?: string;
    password?: string;
  }>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [registeredEmail, setRegisteredEmail] = useState<string | null>(null);
  const [resendMessage, setResendMessage] = useState<string | null>(null);

  const nameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const validateField = (field: 'name' | 'email' | 'password', nextVal?: string) => {
    const candidate = {
      name: field === 'name' ? nextVal ?? name : name,
      email: field === 'email' ? nextVal ?? email : email,
      password: field === 'password' ? nextVal ?? password : password,
    };
    const parsed = registerSchema.safeParse(candidate);
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
    setTouched({ name: true, email: true, password: true });

    const parsed = registerSchema.safeParse({ name, email, password });
    if (!parsed.success) {
      const nextErrors: { name?: string; email?: string; password?: string } = {};
      for (const issue of parsed.error.issues) {
        const key = issue.path[0];
        if (key === 'name' || key === 'email' || key === 'password') {
          if (!nextErrors[key]) {
            nextErrors[key] = issue.message;
          }
        }
      }
      setFieldErrors(nextErrors);
      if (nextErrors.name) nameRef.current?.focus();
      else if (nextErrors.email) emailRef.current?.focus();
      else if (nextErrors.password) passwordRef.current?.focus();
      return;
    }

    setFieldErrors({});
    setIsSubmitting(true);
    try {
      const response = await authApi.register(parsed.data);
      setRegisteredEmail(response.user.email);
    } catch (err) {
      setServerError(extractApiErrorMessage(err, 'Unable to create your account.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResend = async () => {
    if (!registeredEmail) {
      return;
    }
    setResendMessage(null);
    try {
      const resp = await authApi.resendVerification(registeredEmail);
      setResendMessage(resp.message);
    } catch (err) {
      setResendMessage(extractApiErrorMessage(err, 'Failed to resend verification email.'));
    }
  };

  if (registeredEmail) {
    return (
      <AuthCard title="Verify your email" subtitle="One quick step before signing in to FinSight.">
        <div role="status" className="space-y-4">
          <p className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-800 dark:border-green-900 dark:bg-green-950/30 dark:text-green-200">
            We sent a verification link to <strong>{registeredEmail}</strong>. Open the link in your
            inbox to activate your account.
          </p>
          {resendMessage ? (
            <p className="text-sm text-surface-600 dark:text-surface-300">{resendMessage}</p>
          ) : null}
          <div className="flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              onClick={handleResend}
              className="min-h-[44px] flex-1 rounded-lg border border-surface-300 px-4 py-2 text-sm font-medium text-surface-700 hover:bg-surface-100 dark:border-surface-700 dark:text-surface-200 dark:hover:bg-surface-800"
            >
              Resend verification email
            </button>
            <Link
              href="/login"
              className="flex min-h-[44px] flex-1 items-center justify-center rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
            >
              Go to sign in
            </Link>
          </div>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Create your account"
      subtitle="Analyze annual reports and market data with cited findings."
    >
      <div className="space-y-5">
        <GoogleOAuthButton nextPath="/profile" label="Sign up with Google" />

        <div className="relative">
          <div className="absolute inset-0 flex items-center" aria-hidden="true">
            <div className="w-full border-t border-surface-200 dark:border-surface-800" />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-white px-2 text-surface-500 dark:bg-surface-900 dark:text-surface-400">
              Or continue with email
            </span>
          </div>
        </div>

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
              htmlFor="register-name"
              className="block text-sm font-medium text-surface-800 dark:text-surface-200"
            >
              Full name
              <span className="ml-1 text-red-600" aria-hidden="true">
                *
              </span>
            </label>
            <input
              ref={nameRef}
              id="register-name"
              name="name"
              type="text"
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                if (fieldErrors.name) validateField('name', event.target.value);
              }}
              onBlur={() => {
                setTouched((prev) => ({ ...prev, name: true }));
                validateField('name');
              }}
              autoComplete="name"
              enterKeyHint="next"
              required
              maxLength={120}
              aria-invalid={fieldErrors.name ? 'true' : 'false'}
              aria-describedby={fieldErrors.name ? 'register-name-error' : undefined}
              className={`finsight-input min-h-[48px] w-full rounded-lg border px-3.5 py-2.5 text-base text-surface-900 shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 dark:bg-surface-950 dark:text-surface-50 ${
                fieldErrors.name
                  ? 'border-red-600 bg-red-50/50 dark:border-red-500'
                  : 'border-surface-300 bg-white dark:border-surface-700'
              }`}
            />
            {fieldErrors.name ? (
              <p
                id="register-name-error"
                className="flex items-start gap-1.5 text-sm text-red-700 dark:text-red-300"
              >
                <span role="img" aria-label="Error">
                  !
                </span>
                <span>{fieldErrors.name}</span>
              </p>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="register-email"
              className="block text-sm font-medium text-surface-800 dark:text-surface-200"
            >
              Email address
              <span className="ml-1 text-red-600" aria-hidden="true">
                *
              </span>
            </label>
            <span
              id="register-email-hint"
              className="block text-xs text-surface-500 dark:text-surface-400"
            >
              Format: you@example.com
            </span>
            <input
              ref={emailRef}
              id="register-email"
              name="email"
              type="email"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                if (fieldErrors.email) validateField('email', event.target.value);
              }}
              onBlur={() => {
                setTouched((prev) => ({ ...prev, email: true }));
                validateField('email');
              }}
              autoComplete="username"
              spellCheck={false}
              autoCapitalize="none"
              autoCorrect="off"
              enterKeyHint="next"
              required
              aria-invalid={fieldErrors.email ? 'true' : 'false'}
              aria-describedby={
                fieldErrors.email
                  ? 'register-email-hint register-email-error'
                  : 'register-email-hint'
              }
              className={`finsight-input min-h-[48px] w-full rounded-lg border px-3.5 py-2.5 text-base text-surface-900 shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 dark:bg-surface-950 dark:text-surface-50 ${
                fieldErrors.email
                  ? 'border-red-600 bg-red-50/50 dark:border-red-500'
                  : 'border-surface-300 bg-white dark:border-surface-700'
              }`}
            />
            {fieldErrors.email ? (
              <p
                id="register-email-error"
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
            id="register-password"
            name="password"
            label="Password"
            value={password}
            onChange={(val) => {
              setPassword(val);
              if (fieldErrors.password) validateField('password', val);
            }}
            onBlur={() => {
              setTouched((prev) => ({ ...prev, password: true }));
              validateField('password');
            }}
            autoComplete="new-password"
            minLength={12}
            enterKeyHint="done"
            inputRef={passwordRef}
            hintId="register-password-rules"
            hintAbove={
              <PasswordRulesList
                id="register-password-rules"
                password={password}
                showStatus={Boolean(touched.password || password.length > 0)}
              />
            }
            error={fieldErrors.password}
          />

          <button
            type="submit"
            disabled={isSubmitting}
            className="min-h-[48px] w-full rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting ? 'Creating account...' : 'Create account'}
          </button>
        </form>

        <p className="text-center text-sm text-surface-600 dark:text-surface-400">
          Already have an account?{' '}
          <Link
            href="/login"
            className="font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400"
          >
            Sign in
          </Link>
        </p>
      </div>
    </AuthCard>
  );
}
