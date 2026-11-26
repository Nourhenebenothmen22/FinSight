import '@testing-library/jest-dom';
import { afterAll, beforeAll, vi } from 'vitest';

// Mock fetch globally
global.fetch = vi.fn();

// Mock environment variables
vi.stubEnv('NEXT_PUBLIC_API_URL', 'http://localhost:8000');

// Default Next.js App Router navigation mock (overridable per test)
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/',
}));

// Suppress console.error in tests (optional)
const originalError = console.error;
beforeAll(() => {
  console.error = (...args) => {
    if (
      typeof args[0] === 'string' &&
      args[0].includes('Warning: ReactDOM.render is no longer supported')
    ) {
      return;
    }
    originalError.call(console, ...args);
  };
});

afterAll(() => {
  console.error = originalError;
});
