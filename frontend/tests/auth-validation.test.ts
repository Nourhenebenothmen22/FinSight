/** Unit tests for F1 Zod schemas and safe redirect utilities. */

import { describe, expect, it } from 'vitest';
import { sanitizeNextPath } from '@/lib/auth';
import {
  changePasswordSchema,
  getPasswordRequirementsStatus,
  registerSchema,
} from '@/lib/validations/auth';

describe('Auth validation schemas', () => {
  it('normalizes email/name and validates strong passwords', () => {
    const parsed = registerSchema.parse({
      name: '  Alice Analyst  ',
      email: '  Alice@Example.COM ',
      password: 'Valid!Password2026',
    });
    expect(parsed.name).toBe('Alice Analyst');
    expect(parsed.email).toBe('alice@example.com');
  });

  it('rejects weak passwords and reports requirement flags', () => {
    expect(
      registerSchema.safeParse({ name: 'Alice', email: 'a@b.com', password: 'weak' }).success
    ).toBe(false);
    const checks = getPasswordRequirementsStatus('Abc1!');
    expect(checks.find((c) => c.label.includes('12 characters'))?.met).toBe(false);
    expect(checks.find((c) => c.label.includes('uppercase'))?.met).toBe(true);
  });

  it('enforces distinct new password in changePasswordSchema', () => {
    const same = changePasswordSchema.safeParse({
      current_password: 'Same!Password2026',
      new_password: 'Same!Password2026',
      requireCurrentPassword: true,
    });
    expect(same.success).toBe(false);
  });

  it('blocks open redirects via sanitizeNextPath', () => {
    expect(sanitizeNextPath('/profile')).toBe('/profile');
    expect(sanitizeNextPath('https://evil.example')).toBe('/profile');
    expect(sanitizeNextPath('//evil.example')).toBe('/profile');
    expect(sanitizeNextPath('/\\evil.example')).toBe('/profile');
  });
});
