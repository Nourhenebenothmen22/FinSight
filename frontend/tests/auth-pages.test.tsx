/** Component and integration tests for F1 auth pages, AuthProvider, and ProfilePage. */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import * as nextNavigation from 'next/navigation';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ForgotPasswordPage from '@/app/forgot-password/page';
import LoginPage from '@/app/login/page';
import ProfilePage from '@/app/profile/page';
import RegisterPage from '@/app/register/page';
import { AuthProvider } from '@/components/auth/AuthProvider';
import { api, ApiError } from '@/lib/api';
import { authApi, AuthUser, SessionInfo, TokenResponse } from '@/lib/auth';

const mockUser: AuthUser = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'alice@example.com',
  name: 'Alice Analyst',
  email_verified_at: '2026-11-26T12:00:00Z',
  oauth_provider: null,
  has_password: true,
  is_active: true,
  last_login_at: '2026-11-26T13:00:00Z',
  created_at: '2026-11-26T10:00:00Z',
};

const mockTokens: TokenResponse = {
  access_token: 'access-token-123',
  token_type: 'bearer',
  expires_in: 1800,
  user: mockUser,
};

describe('F1 Auth Pages', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi
      .mocked(nextNavigation.useSearchParams)
      .mockImplementation?.(() => new URLSearchParams() as never);
  });

  it('RegisterPage enforces validation, toggles password visibility, and submits cleanly', async () => {
    const registerSpy = vi.spyOn(authApi, 'register').mockResolvedValue({
      message: 'Account created.',
      user: { ...mockUser, email_verified_at: null },
    });

    render(
      <AuthProvider skipInitialRefresh>
        <RegisterPage />
      </AuthProvider>
    );

    const passwordInput = screen.getByLabelText(/Password/i, { selector: 'input' });
    expect(passwordInput).toHaveAttribute('autocomplete', 'new-password');
    expect(passwordInput).toHaveAttribute('type', 'password');

    // Toggle password visibility
    const toggleBtn = screen.getByRole('button', { name: /show password/i });
    fireEvent.click(toggleBtn);
    expect(passwordInput).toHaveAttribute('type', 'text');
    expect(toggleBtn).toHaveAttribute('aria-pressed', 'true');

    // Submit valid values
    fireEvent.change(screen.getByLabelText(/Full name/i), { target: { value: 'Alice Analyst' } });
    fireEvent.change(screen.getByLabelText(/Email address/i), {
      target: { value: 'alice@example.com' },
    });
    fireEvent.change(passwordInput, { target: { value: 'Strong!Pass2026#' } });
    fireEvent.click(screen.getByRole('button', { name: /create account/i }));

    await waitFor(() => {
      expect(registerSpy).toHaveBeenCalledWith({
        name: 'Alice Analyst',
        email: 'alice@example.com',
        password: 'Strong!Pass2026#',
      });
    });

    await waitFor(() => {
      expect(screen.getByText(/Verify your email/i)).toBeInTheDocument();
    });
  });

  it('LoginPage shows inline resend verification CTA on unverified 403 and renders disclaimer', async () => {
    vi.spyOn(authApi, 'login').mockRejectedValue(
      new ApiError('API error: 403 Forbidden', 403, { detail: 'Email address is not verified' })
    );
    const resendSpy = vi.spyOn(authApi, 'resendVerification').mockResolvedValue({
      message: 'Verification link sent.',
    });

    render(
      <AuthProvider skipInitialRefresh>
        <LoginPage />
      </AuthProvider>
    );

    const emailInput = screen.getByLabelText(/Email address/i);
    const passwordInput = screen.getByLabelText(/Password/i, { selector: 'input' });
    expect(emailInput).toHaveAttribute('autocomplete', 'username');
    expect(passwordInput).toHaveAttribute('autocomplete', 'current-password');

    fireEvent.change(emailInput, { target: { value: 'alice@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'Strong!Pass2026#' } });
    fireEvent.click(screen.getByRole('button', { name: /^Sign in$/i }));

    await waitFor(() => {
      expect(screen.getByText(/Email address is not verified/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Resend verification email/i }));
    await waitFor(() => {
      expect(resendSpy).toHaveBeenCalledWith('alice@example.com');
    });
    expect(screen.getByText(/not investment advice/i)).toBeInTheDocument();
  });

  it('ForgotPasswordPage submits email and displays confirmation copy', async () => {
    const forgotSpy = vi.spyOn(authApi, 'forgotPassword').mockResolvedValue({
      message: 'If an account exists for this email, a password reset link has been sent.',
    });

    render(
      <AuthProvider skipInitialRefresh>
        <ForgotPasswordPage />
      </AuthProvider>
    );

    fireEvent.change(screen.getByLabelText(/Email address/i), {
      target: { value: 'alice@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Send reset link/i }));

    await waitFor(() => {
      expect(forgotSpy).toHaveBeenCalledWith('alice@example.com');
      expect(screen.getByText(/password reset link has been sent/i)).toBeInTheDocument();
    });
  });

  it('ProfilePage displays account info, sessions, F2 boundary notice, and handles revoke', async () => {
    vi.spyOn(authApi, 'refresh').mockResolvedValue(mockTokens);
    const sessions: SessionInfo[] = [
      {
        id: 'sess-1',
        user_agent: 'Mozilla/5.0 Test',
        ip_address: '127.0.0.1',
        created_at: '2026-11-26T12:00:00Z',
        expires_at: '2026-12-03T12:00:00Z',
        is_current: true,
      },
    ];
    vi.spyOn(authApi, 'listSessions').mockResolvedValue(sessions);
    const revokeSpy = vi.spyOn(authApi, 'revokeSession').mockResolvedValue(undefined);

    render(
      <AuthProvider>
        <ProfilePage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Account Profile')).toBeInTheDocument();
    });

    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    expect(screen.getByText('Verified email')).toBeInTheDocument();
    expect(screen.getByText(/Mozilla\/5\.0 Test/)).toBeInTheDocument();
    expect(screen.getByText(/introduced in/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Revoke' }));
    await waitFor(() => {
      expect(revokeSpy).toHaveBeenCalledWith('sess-1');
    });
  });

  it('AuthProvider uses single-flight refresh lock across concurrent 401 responses', async () => {
    let refreshCalls = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/v1/auth/refresh')) {
        refreshCalls += 1;
        return new Response(JSON.stringify({ ...mockTokens, access_token: 'fresh-token-456' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        });
      }
      const headers = new Headers(init?.headers);
      if (headers.get('authorization') === 'Bearer fresh-token-456') {
        return new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        });
      }
      return new Response(JSON.stringify({ detail: 'Expired' }), {
        status: 401,
        headers: { 'content-type': 'application/json' },
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <AuthProvider skipInitialRefresh>
        <div data-testid="mounted" />
      </AuthProvider>
    );

    const [r1, r2] = await Promise.all([
      api.get<{ ok: boolean }>('/api/v1/auth/me'),
      api.get<{ ok: boolean }>('/api/v1/auth/sessions'),
    ]);
    expect(r1).toEqual({ ok: true });
    expect(r2).toEqual({ ok: true });
    expect(refreshCalls).toBe(1);
  });
});
