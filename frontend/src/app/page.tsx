'use client';

import { useEffect, useState } from 'react';
import { HealthStatus } from '@/components/HealthStatus';
import { LegalDisclaimer } from '@/components/LegalDisclaimer';
import { Navbar } from '@/components/Navbar';
import { ApiError, HealthResponse, healthApi } from '@/lib/api';

export default function HomePage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchHealth() {
      try {
        const data = await healthApi.check();
        setHealth(data);
      } catch (err) {
        if (
          err instanceof ApiError &&
          err.data &&
          typeof err.data === 'object' &&
          'checks' in err.data
        ) {
          setHealth(err.data as HealthResponse);
        } else {
          setError(err instanceof Error ? err.message : 'Failed to fetch health');
        }
      } finally {
        setLoading(false);
      }
    }

    fetchHealth();
  }, []);

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-surface-50 dark:bg-surface-950">
        <div className="text-center">
          <div className="mx-auto mb-4 h-12 w-12 animate-spin rounded-full border-4 border-primary-500 border-t-transparent" />
          <p className="text-surface-600 dark:text-surface-400">Loading health status...</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-surface-50 dark:bg-surface-950">
      <Navbar />
      <div className="mx-auto max-w-4xl px-4 py-16 sm:px-6 lg:px-8">
        {/* Hero Section */}
        <section className="mb-16 text-center">
          <h1 className="mb-6 animate-fade-in text-4xl font-bold text-surface-900 sm:text-5xl lg:text-6xl dark:text-surface-50">
            FinSight
          </h1>
          <p className="mx-auto mb-8 max-w-2xl animate-slide-up text-xl text-surface-600 sm:text-2xl dark:text-surface-400">
            AI-powered financial analysis with source-backed citations
          </p>
          <div className="flex animate-slide-up flex-col items-center justify-center gap-4 sm:flex-row">
            <a
              href="/api/backend/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-lg bg-primary-600 px-6 py-3 font-medium text-white transition-colors hover:bg-primary-700"
            >
              API Documentation
            </a>
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-lg border-2 border-surface-300 px-6 py-3 font-medium text-surface-700 transition-colors hover:bg-surface-100 dark:border-surface-600 dark:text-surface-300 dark:hover:bg-surface-800"
            >
              View on GitHub
            </a>
          </div>
        </section>

        {/* Health Status */}
        <section className="mb-16">
          <h2 className="mb-6 text-2xl font-semibold text-surface-900 dark:text-surface-50">
            System Health
          </h2>
          {error ? (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
              <p className="text-red-700 dark:text-red-300">
                Failed to load health status: {error}
              </p>
            </div>
          ) : health ? (
            <HealthStatus health={health} />
          ) : (
            <div className="rounded-lg border border-surface-200 bg-surface-100 p-4 dark:border-surface-700 dark:bg-surface-800">
              <p className="text-surface-600 dark:text-surface-400">No health data available</p>
            </div>
          )}
        </section>

        {/* Feature Cards */}
        <section className="mb-12">
          <h2 className="mb-6 text-2xl font-semibold text-surface-900 dark:text-surface-50">
            Platform Capabilities
          </h2>
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            {features.map((feature) => (
              <FeatureCard key={feature.title} feature={feature} />
            ))}
          </div>
        </section>

        {/* Mandatory Legal Disclaimer */}
        <LegalDisclaimer />
      </div>
    </main>
  );
}

interface Feature {
  title: string;
  description: string;
  icon: React.ReactNode;
}

const features: Feature[] = [
  {
    title: 'Multi-tenant SaaS',
    description: 'Organizations, roles, invitations, and row-level security for data isolation',
    icon: (
      <svg className="h-8 w-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"
        />
      </svg>
    ),
  },
  {
    title: 'Document Ingestion',
    description:
      'PDF upload, Docling parsing, VLM chart interpretation, structured table extraction',
    icon: (
      <svg className="h-8 w-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
        />
      </svg>
    ),
  },
  {
    title: 'Multi-Agent Analysis',
    description: 'Supervisor, RAG, Market Data, News Sentiment, Quant/ML, Writer, Critic agents',
    icon: (
      <svg className="h-8 w-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M13 10V3L4 14h7v7l9-11h-7z"
        />
      </svg>
    ),
  },
  {
    title: 'Citation-Backed Reports',
    description: 'Every figure traced to source page or external provider with retrieval timestamp',
    icon: (
      <svg className="h-8 w-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
        />
      </svg>
    ),
  },
  {
    title: 'Writer ↔ Critic Loop',
    description: 'Automated verification with plan-limited revisions and human approval gate',
    icon: (
      <svg className="h-8 w-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
        />
      </svg>
    ),
  },
  {
    title: 'Flexible LLM Routing',
    description: 'Role-based provider selection with fallback, cost tracking, and budget guards',
    icon: (
      <svg className="h-8 w-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
        />
      </svg>
    ),
  },
];

function FeatureCard({ feature }: { feature: Feature }) {
  return (
    <div className="rounded-xl border border-surface-200 bg-white p-6 transition-shadow hover:shadow-lg dark:border-surface-700 dark:bg-surface-900">
      <div className="mb-4 text-primary-600 dark:text-primary-400">{feature.icon}</div>
      <h3 className="mb-2 text-lg font-semibold text-surface-900 dark:text-surface-50">
        {feature.title}
      </h3>
      <p className="text-sm leading-relaxed text-surface-600 dark:text-surface-400">
        {feature.description}
      </p>
    </div>
  );
}
