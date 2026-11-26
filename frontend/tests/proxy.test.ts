/** Tests for the Next.js runtime backend proxy forwarding cookies and errors. */

import { NextRequest } from 'next/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { POST } from '@/app/api/backend/[...path]/route';

describe('Backend Proxy Route', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('forwards cookies upstream and preserves multiple Set-Cookie headers downstream', async () => {
    const upstreamHeaders = new Headers({ 'content-type': 'application/json' });
    (upstreamHeaders as Headers & { getSetCookie?: () => string[] }).getSetCookie = () => [
      'finsight_refresh_token=abc; Path=/api; HttpOnly; SameSite=lax',
      'other_cookie=xyz; Path=/',
    ];

    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      headers: upstreamHeaders,
      arrayBuffer: async () => new TextEncoder().encode('{"ok":true}').buffer,
    });
    vi.stubGlobal('fetch', fetchMock);

    const request = new NextRequest('http://localhost:3000/api/backend/api/v1/auth/login', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        cookie: 'finsight_refresh_token=old',
        origin: 'http://localhost:3000',
        'x-tenant-id': '11111111-1111-1111-1111-111111111111',
      },
      body: JSON.stringify({ email: 'a@b.com', password: 'secret' }),
    });

    const response = await POST(request, { params: { path: ['api', 'v1', 'auth', 'login'] } });
    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const [, init] = fetchMock.mock.calls[0];
    const forwardedHeaders = init.headers as Headers;
    expect(forwardedHeaders.get('cookie')).toBe('finsight_refresh_token=old');
    expect(forwardedHeaders.get('origin')).toBe('http://localhost:3000');
    expect(forwardedHeaders.get('x-tenant-id')).toBe('11111111-1111-1111-1111-111111111111');
    expect(response.headers.get('set-cookie')).toContain('finsight_refresh_token=abc');
  });

  it('returns 502 JSON error when backend is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED')));

    const request = new NextRequest('http://localhost:3000/api/backend/health', {
      method: 'POST',
    });

    const response = await POST(request, { params: { path: ['health'] } });
    expect(response.status).toBe(502);
    expect(await response.json()).toEqual({ detail: 'Backend service unavailable' });
  });
});
