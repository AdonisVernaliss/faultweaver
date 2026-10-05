import { api } from './api';
import type { Exchange, ExchangeList } from './types';

type RequestPage = ExchangeList & { unfilteredTotal: number };

export function createRequestPageLoader() {
  let generation = 0;
  return {
    invalidate() {
      generation += 1;
    },
    async load(engagementId: string, filter: string, source: string, offset = 0): Promise<RequestPage | null> {
      const current = ++generation;
      const params = new URLSearchParams({ limit: '100', offset: String(offset) });
      if (filter.trim()) params.set('q', filter.trim());
      if (source) params.set('source', source);
      try {
        const path = `engagements/${engagementId}/requests`;
        const [page, unfiltered] = await Promise.all([
          api<ExchangeList>(`${path}?${params}`),
          filter.trim() || source ? api<ExchangeList>(`${path}?limit=1`) : null
        ]);
        return current === generation ? { ...page, unfilteredTotal: unfiltered?.total ?? page.total } : null;
      } catch (error) {
        if (current !== generation) return null;
        throw error;
      }
    }
  };
}

export function mergeRequestPages(existing: Exchange[], incoming: Exchange[]): Exchange[] {
  const known = new Set(existing.map(request => request.id));
  return [...existing, ...incoming.filter(request => !known.has(request.id))];
}
