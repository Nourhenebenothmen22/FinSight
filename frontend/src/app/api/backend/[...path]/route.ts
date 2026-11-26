import { NextRequest, NextResponse } from 'next/server';

const getBackendBaseUrl = (): string =>
  (
    process.env.BACKEND_INTERNAL_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    'http://localhost:8000'
  ).replace(/\/$/, '');

async function proxyRequest(
  request: NextRequest,
  context: { params: { path: string[] } }
): Promise<NextResponse> {
  const path = context.params.path.join('/');
  const search = request.nextUrl.search;
  const targetUrl = `${getBackendBaseUrl()}/${path}${search}`;

  const headers = new Headers();
  for (const headerName of [
    'content-type',
    'authorization',
    'cookie',
    'origin',
    'referer',
    'user-agent',
    'x-tenant-id',
  ]) {
    const value = request.headers.get(headerName);
    if (value) {
      headers.set(headerName, value);
    }
  }

  const forwardedFor = request.headers.get('x-forwarded-for');
  if (forwardedFor) {
    headers.set('x-forwarded-for', forwardedFor);
  } else if (request.ip) {
    headers.set('x-forwarded-for', request.ip);
  }

  try {
    const hasBody = !['GET', 'HEAD'].includes(request.method);
    const upstream = await fetch(targetUrl, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: 'no-store',
      redirect: 'manual',
    });

    const body = await upstream.arrayBuffer();
    const responseHeaders = new Headers();
    for (const headerName of [
      'content-type',
      'location',
      'retry-after',
      'x-ratelimit-limit',
      'x-ratelimit-remaining',
      'x-ratelimit-reset',
      'x-request-id',
    ]) {
      const value = upstream.headers.get(headerName);
      if (value) {
        responseHeaders.set(headerName, value);
      }
    }

    const upstreamWithSetCookie = upstream.headers as Headers & {
      getSetCookie?: () => string[];
    };
    const setCookies = upstreamWithSetCookie.getSetCookie?.() ?? [];
    if (setCookies.length > 0) {
      for (const cookieValue of setCookies) {
        responseHeaders.append('set-cookie', cookieValue);
      }
    } else {
      const singleSetCookie = upstream.headers.get('set-cookie');
      if (singleSetCookie) {
        responseHeaders.append('set-cookie', singleSetCookie);
      }
    }

    return new NextResponse(body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return NextResponse.json({ detail: 'Backend service unavailable' }, { status: 502 });
  }
}

export const dynamic = 'force-dynamic';

export async function GET(
  request: NextRequest,
  context: { params: { path: string[] } }
): Promise<NextResponse> {
  return proxyRequest(request, context);
}

export async function POST(
  request: NextRequest,
  context: { params: { path: string[] } }
): Promise<NextResponse> {
  return proxyRequest(request, context);
}

export async function PUT(
  request: NextRequest,
  context: { params: { path: string[] } }
): Promise<NextResponse> {
  return proxyRequest(request, context);
}

export async function PATCH(
  request: NextRequest,
  context: { params: { path: string[] } }
): Promise<NextResponse> {
  return proxyRequest(request, context);
}

export async function DELETE(
  request: NextRequest,
  context: { params: { path: string[] } }
): Promise<NextResponse> {
  return proxyRequest(request, context);
}
