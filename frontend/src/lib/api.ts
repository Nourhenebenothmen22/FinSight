/** API client and types for FinSight Frontend. */

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

async function fetchJson<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${endpoint}`;

  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

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
  get: <T>(endpoint: string) => fetchJson<T>(endpoint, { method: 'GET' }),
  post: <T>(endpoint: string, body: unknown) =>
    fetchJson<T>(endpoint, { method: 'POST', body: JSON.stringify(body) }),
  put: <T>(endpoint: string, body: unknown) =>
    fetchJson<T>(endpoint, { method: 'PUT', body: JSON.stringify(body) }),
  patch: <T>(endpoint: string, body: unknown) =>
    fetchJson<T>(endpoint, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: <T>(endpoint: string) => fetchJson<T>(endpoint, { method: 'DELETE' }),
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
