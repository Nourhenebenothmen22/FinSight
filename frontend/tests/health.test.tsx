/** Tests for health check functionality. */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { HealthStatus } from '@/components/HealthStatus';
import HomePage from '@/app/page';
import { healthApi, HealthResponse } from '@/lib/api';

// Mock the API module
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    healthApi: {
      check: vi.fn(),
      ready: vi.fn(),
      live: vi.fn(),
    },
    api: {
      get: vi.fn(),
      post: vi.fn(),
    },
  };
});

const mockHealthResponse: HealthResponse = {
  status: 'healthy',
  service: 'FinSight',
  version: '0.1.0',
  environment: 'development',
  checks: {
    database: 'healthy',
    redis: 'healthy',
    qdrant: 'healthy',
    storage: 'healthy',
  },
};

describe('HealthStatus Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders overall status as healthy', () => {
    render(<HealthStatus health={mockHealthResponse} />);

    expect(screen.getByText('Overall Status')).toBeInTheDocument();
    expect(screen.getByText('FinSight v0.1.0 • development')).toBeInTheDocument();
    expect(screen.getByText('Healthy')).toBeInTheDocument();
    expect(screen.getByRole('status', { name: /healthy/i })).toBeInTheDocument();
  });

  it('renders degraded status correctly', () => {
    const degradedHealth = { ...mockHealthResponse, status: 'degraded' as const };
    render(<HealthStatus health={degradedHealth} />);

    expect(screen.getByText('Degraded')).toBeInTheDocument();
  });

  it('renders unhealthy status correctly', () => {
    const unhealthyHealth = { ...mockHealthResponse, status: 'unhealthy' as const };
    render(<HealthStatus health={unhealthyHealth} />);

    expect(screen.getByText('Unhealthy')).toBeInTheDocument();
  });

  it('renders all dependency checks', () => {
    render(<HealthStatus health={mockHealthResponse} />);

    expect(screen.getByText('Dependency Checks')).toBeInTheDocument();
    expect(screen.getByText('database')).toBeInTheDocument();
    expect(screen.getByText('redis')).toBeInTheDocument();
    expect(screen.getByText('qdrant')).toBeInTheDocument();
    expect(screen.getByText('storage')).toBeInTheDocument();
    // 4 detail texts + 4 status pills = 8 exact lowercase "healthy" spans/paragraphs
    expect(screen.getAllByText('healthy')).toHaveLength(8);
  });

  it('shows detailed status for each check', () => {
    const healthWithDetails = {
      ...mockHealthResponse,
      checks: {
        database: 'healthy: connection ok',
        redis: 'healthy: ping ok',
        qdrant: 'unhealthy: connection refused',
        storage: 'healthy: live',
      },
    };

    render(<HealthStatus health={healthWithDetails} />);

    expect(screen.getByText('connection ok')).toBeInTheDocument();
    expect(screen.getByText('ping ok')).toBeInTheDocument();
    expect(screen.getByText('connection refused')).toBeInTheDocument();
    expect(screen.getByText('live')).toBeInTheDocument();
  });
});

describe('healthApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls correct endpoint for health check', async () => {
    vi.mocked(healthApi.check).mockResolvedValue(mockHealthResponse);

    const result = await healthApi.check();

    expect(healthApi.check).toHaveBeenCalledTimes(1);
    expect(result).toEqual(mockHealthResponse);
  });

  it('calls correct endpoint for readiness', async () => {
    vi.mocked(healthApi.ready).mockResolvedValue(mockHealthResponse);

    const result = await healthApi.ready();

    expect(healthApi.ready).toHaveBeenCalledTimes(1);
    expect(result).toEqual(mockHealthResponse);
  });

  it('calls correct endpoint for liveness', async () => {
    vi.mocked(healthApi.live).mockResolvedValue({ status: 'alive' });

    const result = await healthApi.live();

    expect(healthApi.live).toHaveBeenCalledTimes(1);
    expect(result).toEqual({ status: 'alive' });
  });
});

describe('HomePage Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders health status and mandatory disclaimer after fetch', async () => {
    vi.mocked(healthApi.check).mockResolvedValue(mockHealthResponse);

    render(<HomePage />);
    expect(screen.getByText('Loading health status...')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('System Health')).toBeInTheDocument();
    });
    expect(screen.getByText(/not investment advice/i)).toBeInTheDocument();
  });
});
