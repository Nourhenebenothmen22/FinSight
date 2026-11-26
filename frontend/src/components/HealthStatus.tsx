'use client';

import { HealthResponse } from '@/lib/api';

interface HealthStatusProps {
  health: HealthResponse;
}

export function HealthStatus({ health }: HealthStatusProps) {
  const statusColors = {
    healthy: 'bg-green-500',
    degraded: 'bg-yellow-500',
    unhealthy: 'bg-red-500',
  };

  const statusLabels = {
    healthy: 'Healthy',
    degraded: 'Degraded',
    unhealthy: 'Unhealthy',
  };

  const checkStatus = (value: string) => {
    if (value.startsWith('healthy')) return 'healthy';
    if (value.startsWith('degraded')) return 'degraded';
    return 'unhealthy';
  };

  return (
    <div className="space-y-4">
      {/* Overall Status */}
      <div className="rounded-xl border border-surface-200 bg-white p-6 dark:border-surface-700 dark:bg-surface-900">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-lg font-semibold text-surface-900 dark:text-surface-50">
              Overall Status
            </h3>
            <p className="mt-1 text-sm text-surface-500 dark:text-surface-400">
              {health.service} v{health.version} • {health.environment}
            </p>
          </div>
          <div className="flex items-center gap-4">
            <span
              role="status"
              aria-label={`System status: ${statusLabels[health.status]}`}
              className={`rounded-full px-4 py-2 text-sm font-medium text-white ${statusColors[health.status]}`}
            >
              {statusLabels[health.status]}
            </span>
          </div>
        </div>
      </div>

      {/* Dependency Checks */}
      <div className="overflow-hidden rounded-xl border border-surface-200 bg-white dark:border-surface-700 dark:bg-surface-900">
        <div className="border-b border-surface-200 px-6 py-4 dark:border-surface-700">
          <h3 className="text-lg font-semibold text-surface-900 dark:text-surface-50">
            Dependency Checks
          </h3>
        </div>
        <div className="divide-y divide-surface-200 dark:divide-surface-700">
          {Object.entries(health.checks).map(([name, status]) => {
            const checkState = checkStatus(status);
            const stateColors = {
              healthy: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300',
              degraded: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300',
              unhealthy: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300',
            };

            const stateIcons = {
              healthy: (
                <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                    clipRule="evenodd"
                  />
                </svg>
              ),
              degraded: (
                <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                    clipRule="evenodd"
                  />
                </svg>
              ),
              unhealthy: (
                <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                    clipRule="evenodd"
                  />
                </svg>
              ),
            };

            const detail = status.includes(': ') ? status.split(': ').slice(1).join(': ') : status;

            return (
              <div
                key={name}
                className="flex items-center justify-between px-6 py-4 hover:bg-surface-50 dark:hover:bg-surface-800/50"
              >
                <div className="flex items-center gap-3">
                  <span className={`rounded-lg p-2 ${stateColors[checkState]}`}>
                    {stateIcons[checkState]}
                  </span>
                  <div>
                    <p className="font-medium capitalize text-surface-900 dark:text-surface-50">
                      {name}
                    </p>
                    <p className="text-sm text-surface-500 dark:text-surface-400">{detail}</p>
                  </div>
                </div>
                <span
                  className={`rounded-full px-3 py-1 text-xs font-medium ${stateColors[checkState]}`}
                >
                  {checkState}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
