import { FAULTWEAVER_API_URL } from '$app/env/private';
import type { RequestHandler } from './$types';

async function proxy({ request, params, url }: Parameters<RequestHandler>[0]): Promise<Response> {
  const backend = FAULTWEAVER_API_URL ?? 'http://localhost:8000';
  const target = new URL(`/api/${params.path ?? ''}`, backend);
  target.search = url.search;

  const headers = new Headers(request.headers);
  headers.delete('host');
  headers.delete('content-length');

  try {
    return await fetch(target, {
      method: request.method,
      headers,
      body: request.method === 'GET' || request.method === 'HEAD' ? undefined : request.body,
      duplex: 'half'
    } as RequestInit);
  } catch {
    return Response.json({ detail: 'Faultweaver API is unavailable' }, { status: 502 });
  }
}

export const GET: RequestHandler = proxy;
export const POST: RequestHandler = proxy;
export const PATCH: RequestHandler = proxy;
export const PUT: RequestHandler = proxy;
export const DELETE: RequestHandler = proxy;
