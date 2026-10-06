import { afterEach, describe, expect, it, vi } from 'vitest';
vi.mock('$app/env/private', () => ({ FAULTWEAVER_API_URL: 'http://backend.test:8000' }));
import { GET, POST, PATCH, PUT, DELETE } from '../routes/api/[...path]/+server';

describe('workspace API proxy', () => {
  afterEach(() => vi.unstubAllGlobals());
  it.each([['GET', GET], ['POST', POST], ['PATCH', PATCH], ['PUT', PUT], ['DELETE', DELETE]] as const)(
    'forwards %s to the configured backend', async (method, handler) => {
      const fetchMock = vi.fn(async () => Response.json({ ok: true }));
      vi.stubGlobal('fetch', fetchMock);
      const response = await handler({
        request: new Request('http://localhost:5173/api/engagements/sample?sort=id', {
          method, headers: { 'content-type': 'application/json' }, ...(method === 'GET' ? {} : { body: '{}' })
        }),
        params: { path: 'engagements/sample' }, url: new URL('http://localhost:5173/api/engagements/sample?sort=id')
      } as Parameters<typeof handler>[0]);
      expect(response.status).toBe(200);
      const [target, init] = (fetchMock.mock.calls as unknown as [URL, RequestInit][])[0];
      expect(String(target)).toBe('http://backend.test:8000/api/engagements/sample?sort=id');
      expect(init.method).toBe(method);
    }
  );
  it('returns a safe actionable unavailable response', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('synthetic-private-diagnostic'); }));
    const response = await GET({ request: new Request('http://localhost/api/health'),
      params: { path: 'health' }, url: new URL('http://localhost/api/health') } as Parameters<typeof GET>[0]);
    expect(response.status).toBe(502);
    expect(await response.text()).toBe('{"detail":"Faultweaver API is unavailable"}');
  });
});
