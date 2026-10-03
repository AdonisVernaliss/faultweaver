import { afterEach, describe, expect, it, vi } from 'vitest';

import { api } from './api';
import type { Evidence, Finding, Retest } from './types';

describe('finding lifecycle client flow', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('promotes a candidate, captures evidence, updates status, and records a retest', async () => {
    const finding = { id: 'finding-1', display_id: 'FW-001' } as Finding;
    const evidence = { id: 'evidence-1', display_id: 'EV-001' } as Evidence;
    const retest = { id: 'retest-1', display_id: 'RT-001', status: 'Fixed' } as Retest;
    const responses = [finding, evidence, finding, retest];
    const paths: string[] = [];
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      paths.push(String(input));
      return new Response(JSON.stringify(responses.shift()), {
        status: 201,
        headers: { 'content-type': 'application/json' }
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const promoted = await api<Finding>('engagements/eng-1/candidates/candidate-1/promote', {
      method: 'POST', body: JSON.stringify({ severity: 'High' })
    });
    const captured = await api<Evidence>('engagements/eng-1/evidence', {
      method: 'POST', body: JSON.stringify({
        evidence_type: 'Response Comparison', title: 'Original comparison',
        source_comparison_id: 'comparison-1', finding_id: promoted.id
      })
    });
    await api<Finding>(`engagements/eng-1/findings/${promoted.id}`, {
      method: 'PATCH', body: JSON.stringify({ status: 'Ready for Retest' })
    });
    const verified = await api<Retest>(`engagements/eng-1/findings/${promoted.id}/retests`, {
      method: 'POST', body: JSON.stringify({ status: 'Fixed', evidence_ids: [captured.id] })
    });

    expect([promoted.display_id, captured.display_id, verified.display_id]).toEqual([
      'FW-001', 'EV-001', 'RT-001'
    ]);
    expect(paths).toEqual([
      '/api/engagements/eng-1/candidates/candidate-1/promote',
      '/api/engagements/eng-1/evidence',
      '/api/engagements/eng-1/findings/finding-1',
      '/api/engagements/eng-1/findings/finding-1/retests'
    ]);
  });
});
