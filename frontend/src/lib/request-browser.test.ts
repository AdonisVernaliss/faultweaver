import { afterEach, expect, it, vi } from 'vitest';
import { createRequestPageLoader, mergeRequestPages } from './request-browser';
import type { Exchange } from './types';

afterEach(() => vi.unstubAllGlobals());

it('queries the server for older matching traffic and subsequent pages', async () => {
  const fetchMock = vi.fn(async (input: string) => new Response(JSON.stringify(
    input.endsWith('?limit=1') ? { items: [], total: 300 } : { items: [{ id: 'older' }], total: 241 }
  )));
  vi.stubGlobal('fetch', fetchMock);
  const loader = createRequestPageLoader();
  expect(await loader.load('eng-1', 'note=Last & plus+', 'har', 100)).toEqual({
    items: [{ id: 'older' }], total: 241, unfilteredTotal: 300
  });
  const url = new URL(fetchMock.mock.calls[0][0], 'http://localhost');
  expect(url.pathname).toBe('/api/engagements/eng-1/requests');
  expect(Object.fromEntries(url.searchParams)).toEqual({
    q: 'note=Last & plus+', source: 'har', offset: '100', limit: '100'
  });
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

it('discards stale search results and invalidated engagement loads', async () => {
  const pending: ((response: Response) => void)[] = [];
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => pending.push(resolve))));
  const loader = createRequestPageLoader();
  const old = loader.load('old-eng', '', '', 0);
  const current = loader.load('new-eng', '', '', 0);
  pending[1](new Response(JSON.stringify({ items: [{ id: 'new' }], total: 1 })));
  expect(await current).toEqual({ items: [{ id: 'new' }], total: 1, unfilteredTotal: 1 });
  pending[0](new Response(JSON.stringify({ items: [{ id: 'old' }], total: 1 })));
  expect(await old).toBeNull();
  const invalidated = loader.load('new-eng', '', '', 0);
  loader.invalidate();
  pending[2](new Response(JSON.stringify({ items: [], total: 0 })));
  expect(await invalidated).toBeNull();
});

it('does not duplicate rows when new captures shift an offset page', () => {
  const first = [{ id: 'a' }, { id: 'b' }] as Exchange[];
  expect(mergeRequestPages(first, [{ id: 'b' }, { id: 'c' }] as Exchange[]).map(r => r.id)).toEqual(['a', 'b', 'c']);
  expect(first).toHaveLength(2);
});
