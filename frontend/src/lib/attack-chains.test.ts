import { afterEach, describe, expect, it, vi } from 'vitest';

import { api } from './api';
import type { AttackChain } from './types';

describe('attack chain client flow', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('creates, composes, reorders, evidences, and validates an attack chain', async () => {
    const draft = { id: 'chain-1', display_id: 'AC-001', status: 'Draft' } as AttackChain;
    const validated = { ...draft, status: 'Validated' } as AttackChain;
    const responses = [draft, draft, draft, draft, draft, draft, validated];
    const requests: { path: string; method: string; body: unknown }[] = [];
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      requests.push({
        path: String(input),
        method: init?.method ?? 'GET',
        body: init?.body ? JSON.parse(String(init.body)) : undefined
      });
      return new Response(JSON.stringify(responses.shift()), {
        status: 200,
        headers: { 'content-type': 'application/json' }
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const created = await api<AttackChain>('engagements/eng-1/attack-chains', {
      method: 'POST', body: JSON.stringify({ title: 'Cross-tenant compromise' })
    });
    await api<AttackChain>(`engagements/eng-1/attack-chains/${created.id}/steps`, {
      method: 'POST', body: JSON.stringify({ step_type: 'Finding', finding_id: 'finding-1', position: 1 })
    });
    await api<AttackChain>(`engagements/eng-1/attack-chains/${created.id}/steps`, {
      method: 'POST', body: JSON.stringify({ step_type: 'Intermediate', title: 'Session obtained', position: 2 })
    });
    await api<AttackChain>(`engagements/eng-1/attack-chains/${created.id}/steps`, {
      method: 'POST', body: JSON.stringify({ step_type: 'Finding', finding_id: 'finding-2', position: 3 })
    });
    await api<AttackChain>(`engagements/eng-1/attack-chains/${created.id}/steps/order`, {
      method: 'PUT', body: JSON.stringify({ ordered_step_ids: ['step-2', 'step-1', 'step-3'] })
    });
    await api<AttackChain>(`engagements/eng-1/attack-chains/${created.id}/evidence`, {
      method: 'POST', body: JSON.stringify({ evidence_id: 'evidence-1' })
    });
    const result = await api<AttackChain>(`engagements/eng-1/attack-chains/${created.id}`, {
      method: 'PATCH', body: JSON.stringify({
        resulting_impact: 'Administrative access across tenant boundaries', status: 'Validated'
      })
    });

    expect(created.display_id).toBe('AC-001');
    expect(result.status).toBe('Validated');
    expect(requests.map((request) => [request.method, request.path])).toEqual([
      ['POST', '/api/engagements/eng-1/attack-chains'],
      ['POST', '/api/engagements/eng-1/attack-chains/chain-1/steps'],
      ['POST', '/api/engagements/eng-1/attack-chains/chain-1/steps'],
      ['POST', '/api/engagements/eng-1/attack-chains/chain-1/steps'],
      ['PUT', '/api/engagements/eng-1/attack-chains/chain-1/steps/order'],
      ['POST', '/api/engagements/eng-1/attack-chains/chain-1/evidence'],
      ['PATCH', '/api/engagements/eng-1/attack-chains/chain-1']
    ]);
    expect(requests[4].body).toEqual({ ordered_step_ids: ['step-2', 'step-1', 'step-3'] });
    expect(requests[6].body).toMatchObject({
      resulting_impact: 'Administrative access across tenant boundaries', status: 'Validated'
    });
  });
});
