/** Authentication API client, types, and safe redirect helpers. */

import { api } from '@/lib/api';

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  email_verified_at: string | null;
  oauth_provider: string | null;
  has_password: boolean;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface RegisterResponse {
  message: string;
  user: AuthUser;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token?: string | null;
  user: AuthUser;
  next_path?: string | null;
}

export interface SessionInfo {
  id: string;
  user_agent: string | null;
  ip_address: string | null;
  created_at: string;
  expires_at: string;
  is_current: boolean;
}

export interface MessageResponse {
  message: string;
}

export function sanitizeNextPath(
  nextPath: string | null | undefined,
  fallback = '/profile'
): string {
  if (!nextPath) {
    return fallback;
  }
  const trimmed = nextPath.trim();
  if (
    !trimmed.startsWith('/') ||
    trimmed.startsWith('//') ||
    trimmed.includes('\\') ||
    /[\x00-\x1f\x7f]/.test(trimmed)
  ) {
    return fallback;
  }
  return trimmed;
}

export function getGoogleOAuthStartUrl(nextPath = '/profile'): string {
  const apiPublicOrigin = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(
    /\/$/,
    ''
  );
  const safeNext = encodeURIComponent(sanitizeNextPath(nextPath));
  return `${apiPublicOrigin}/api/v1/auth/google/login?next=${safeNext}`;
}

export const authApi = {
  register: (payload: { name: string; email: string; password: string }) =>
    api.post<RegisterResponse>('/api/v1/auth/register', payload, { skipAuth: true }),

  login: (payload: { email: string; password: string }) =>
    api.post<TokenResponse>('/api/v1/auth/login', payload, { skipAuth: true }),

  refresh: () => api.post<TokenResponse>('/api/v1/auth/refresh', undefined, { skipAuth: true }),

  logout: () => api.post<MessageResponse>('/api/v1/auth/logout', undefined, { skipAuth: true }),

  logoutAll: () => api.post<MessageResponse>('/api/v1/auth/logout-all'),

  verifyEmail: (token: string) =>
    api.post<MessageResponse>('/api/v1/auth/verify', { token }, { skipAuth: true }),

  resendVerification: (email: string) =>
    api.post<MessageResponse>('/api/v1/auth/resend-verification', { email }, { skipAuth: true }),

  forgotPassword: (email: string) =>
    api.post<MessageResponse>('/api/v1/auth/forgot', { email }, { skipAuth: true }),

  resetPassword: (payload: { token: string; new_password: string }) =>
    api.post<MessageResponse>('/api/v1/auth/reset', payload, { skipAuth: true }),

  getMe: () => api.get<AuthUser>('/api/v1/auth/me'),

  updateMe: (payload: { name: string }) => api.patch<AuthUser>('/api/v1/auth/me', payload),

  changePassword: (payload: { current_password?: string; new_password: string }) =>
    api.post<MessageResponse>('/api/v1/auth/change-password', payload),

  listSessions: () => api.get<SessionInfo[]>('/api/v1/auth/sessions'),

  revokeSession: (sessionId: string) => api.delete<void>(`/api/v1/auth/sessions/${sessionId}`),

  exchangeGoogleCode: (code: string) =>
    api.post<TokenResponse>('/api/v1/auth/google/exchange', { code }, { skipAuth: true }),
};
