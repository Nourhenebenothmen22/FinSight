/** API client, auth token refresh lock, and shared response types for FinSight Frontend. */

const API_BASE =
  typeof window !== 'undefined'
    ? '/api/backend'
    : process.env.BACKEND_INTERNAL_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      'http://localhost:8000';

class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public data?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

interface AuthClientHooks {
  getAccessToken: () => string | null;
  refreshAccessToken: () => Promise<string | null>;
  getActiveTenantId?: () => string | null;
}

let authHooks: AuthClientHooks | null = null;
let tenantIdGetter: (() => string | null) | null = null;
let inflightRefresh: Promise<string | null> | null = null;

export function configureAuthClient(hooks: AuthClientHooks | null): void {
  authHooks = hooks;
}

export function configureTenantClient(getter: (() => string | null) | null): void {
  tenantIdGetter = getter;
}

export function extractApiErrorMessage(
  err: unknown,
  fallback = 'An unexpected error occurred.'
): string {
  if (err instanceof ApiError) {
    if (err.data && typeof err.data === 'object' && 'detail' in err.data) {
      const detail = (err.data as { detail?: unknown }).detail;
      if (typeof detail === 'string' && detail.trim()) {
        return detail;
      }
      if (Array.isArray(detail) && detail.length > 0) {
        const first = detail[0];
        if (first && typeof first === 'object' && 'msg' in first && typeof first.msg === 'string') {
          return first.msg;
        }
      }
    }
    return err.message;
  }
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return fallback;
}

async function runSingleFlightRefresh(): Promise<string | null> {
  if (!authHooks) {
    return null;
  }
  if (!inflightRefresh) {
    inflightRefresh = authHooks.refreshAccessToken().finally(() => {
      inflightRefresh = null;
    });
  }
  return inflightRefresh;
}

interface ExtendedRequestInit extends RequestInit {
  skipAuth?: boolean;
  _retried?: boolean;
}

async function fetchJson<T>(endpoint: string, options: ExtendedRequestInit = {}): Promise<T> {
  const { skipAuth = false, _retried = false, ...fetchOptions } = options;
  const url = `${API_BASE}${endpoint}`;

  const headers = new Headers(fetchOptions.headers);
  if (fetchOptions.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  if (!skipAuth && !headers.has('Authorization') && authHooks) {
    const token = authHooks.getAccessToken();
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
  }
  const activeTenantGetter = authHooks?.getActiveTenantId ?? tenantIdGetter;
  if (!skipAuth && !headers.has('X-Tenant-ID') && activeTenantGetter) {
    const tenantId = activeTenantGetter();
    if (tenantId) {
      headers.set('X-Tenant-ID', tenantId);
    }
  }

  const response = await fetch(url, {
    credentials: 'include',
    ...fetchOptions,
    headers,
  });

  if (
    response.status === 401 &&
    !skipAuth &&
    !_retried &&
    !endpoint.startsWith('/api/v1/auth/refresh') &&
    authHooks
  ) {
    const newAccessToken = await runSingleFlightRefresh();
    if (newAccessToken) {
      const retryHeaders = new Headers(fetchOptions.headers);
      if (fetchOptions.body !== undefined && !retryHeaders.has('Content-Type')) {
        retryHeaders.set('Content-Type', 'application/json');
      }
      retryHeaders.set('Authorization', `Bearer ${newAccessToken}`);
      return fetchJson<T>(endpoint, {
        ...options,
        headers: retryHeaders,
        _retried: true,
      });
    }
  }

  if (!response.ok) {
    let data: unknown;
    try {
      data = await response.json();
    } catch {
      data = await response.text();
    }
    throw new ApiError(
      `API error: ${response.status} ${response.statusText}`,
      response.status,
      data
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

export const api = {
  get: <T>(endpoint: string, options?: ExtendedRequestInit) =>
    fetchJson<T>(endpoint, { method: 'GET', ...options }),
  post: <T>(endpoint: string, body?: unknown, options?: ExtendedRequestInit) =>
    fetchJson<T>(endpoint, {
      method: 'POST',
      body: body !== undefined ? JSON.stringify(body) : undefined,
      ...options,
    }),
  put: <T>(endpoint: string, body: unknown, options?: ExtendedRequestInit) =>
    fetchJson<T>(endpoint, { method: 'PUT', body: JSON.stringify(body), ...options }),
  patch: <T>(endpoint: string, body: unknown, options?: ExtendedRequestInit) =>
    fetchJson<T>(endpoint, { method: 'PATCH', body: JSON.stringify(body), ...options }),
  delete: <T>(endpoint: string, options?: ExtendedRequestInit) =>
    fetchJson<T>(endpoint, { method: 'DELETE', ...options }),
};

// -----------------------------------------------------------------------------
// Health Types
// -----------------------------------------------------------------------------
export type HealthStatus = 'healthy' | 'degraded' | 'unhealthy';

export interface HealthResponse {
  status: HealthStatus;
  service: string;
  version: string;
  environment: string;
  checks: Record<string, string>;
}

export interface HealthCheck {
  name: string;
  status: string;
  healthy: boolean;
}

// -----------------------------------------------------------------------------
// Health API
// -----------------------------------------------------------------------------
export const healthApi = {
  check: () => api.get<HealthResponse>('/health'),
  ready: () => api.get<HealthResponse>('/health/ready'),
  live: () => api.get<{ status: string }>('/health/live'),
};

export { ApiError };
