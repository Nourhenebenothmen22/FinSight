import '@testing-library/jest-dom';
import { afterAll, beforeAll, vi } from 'vitest';

// Mock fetch globally
global.fetch = vi.fn();

// Mock environment variables
vi.stubEnv('NEXT_PUBLIC_API_URL', 'http://localhost:8000');

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
