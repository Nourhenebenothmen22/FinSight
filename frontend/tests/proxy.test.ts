/** Tests for the Next.js runtime backend proxy forwarding cookies and errors. */

import { NextRequest } from 'next/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { POST } from '@/app/api/backend/[...path]/route';
import { api, ApiError, extractApiErrorMessage } from '@/lib/api';

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

  it('forwards Retry-After and X-RateLimit-* headers on 429 and surfaces wait time in ApiError', async () => {
    const upstreamHeaders = new Headers({
      'content-type': 'application/json',
      'retry-after': '15',
      'x-ratelimit-limit': '5',
      'x-ratelimit-remaining': '0',
      'x-request-id': 'req-429-test',
    });

    const fetchMock = vi.fn().mockResolvedValue({
      status: 429,
      statusText: 'Too Many Requests',
      ok: false,
      headers: upstreamHeaders,
      json: async () => ({ detail: 'Too many requests. Please try again later.' }),
      arrayBuffer: async () =>
        new TextEncoder().encode(
          JSON.stringify({ detail: 'Too many requests. Please try again later.' })
        ).buffer,
    });
    vi.stubGlobal('fetch', fetchMock);

    const request = new NextRequest('http://localhost:3000/api/backend/api/v1/auth/login', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ email: 'a@b.com', password: 'wrong' }),
    });

    const proxied = await POST(request, { params: { path: ['api', 'v1', 'auth', 'login'] } });
    expect(proxied.status).toBe(429);
    expect(proxied.headers.get('retry-after')).toBe('15');
    expect(proxied.headers.get('x-ratelimit-limit')).toBe('5');
    expect(proxied.headers.get('x-ratelimit-remaining')).toBe('0');
    expect(proxied.headers.get('x-request-id')).toBe('req-429-test');

    let caught: unknown;
    try {
      await api.post(
        '/api/v1/auth/login',
        { email: 'a@b.com', password: 'wrong' },
        { skipAuth: true }
      );
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).status).toBe(429);
    expect((caught as ApiError).retryAfterSeconds).toBe(15);
    expect(extractApiErrorMessage(caught)).toContain('Please wait 15 seconds before trying again.');
  });

  it('appends NextRequest.ip to forwarded-for chain and blocks dot-segment traversal', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      arrayBuffer: async () => new TextEncoder().encode('{"ok":true}').buffer,
    });
    vi.stubGlobal('fetch', fetchMock);

    const request = new NextRequest('http://localhost:3000/api/backend/health', {
      method: 'POST',
      headers: { 'x-forwarded-for': '1.2.3.4' },
    });
    Object.defineProperty(request, 'ip', { value: '198.51.100.77' });

    const okResponse = await POST(request, { params: { path: ['health'] } });
    expect(okResponse.status).toBe(200);
    const forwardedHeaders = fetchMock.mock.calls[0][1].headers as Headers;
    expect(forwardedHeaders.get('x-forwarded-for')).toBe('1.2.3.4, 198.51.100.77');

    fetchMock.mockClear();
    const traversalReq = new NextRequest('http://localhost:3000/api/backend/health', {
      method: 'POST',
    });
    const badResponse = await POST(traversalReq, { params: { path: ['api', '..', 'admin'] } });
    expect(badResponse.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
