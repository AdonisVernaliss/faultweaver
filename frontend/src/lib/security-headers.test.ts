import { describe, expect, it } from 'vitest';
import { handle } from '../hooks.server';

describe('local workspace security headers', () => {
  it('preserves upstream export headers and adds restrictive browser defaults', async () => {
    const result = await handle({
      event: { url: new URL('http://localhost/api/report') },
      resolve: async () => new Response('report', { headers: { 'Content-Disposition': 'attachment; filename="report.html"' } })
    } as unknown as Parameters<typeof handle>[0]);
    expect(result.headers.get('x-content-type-options')).toBe('nosniff');
    expect(result.headers.get('referrer-policy')).toBe('no-referrer');
    expect(result.headers.get('x-frame-options')).toBe('DENY');
    expect(result.headers.get('cache-control')).toBe('no-store');
    expect(result.headers.get('content-disposition')).toContain('attachment');
    expect(await result.text()).toBe('report');
  });
});
