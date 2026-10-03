import { describe, expect, it } from 'vitest';

import { comparisonPayload, comparisonSummary } from './analysis';
import type { ResponseDiff } from './types';

describe('differential analysis presentation', () => {
  it('builds only distinct identity payloads', () => {
    expect(comparisonPayload('tenant-a', 'tenant-b')).toBe(
      '{"identity_a_id":"tenant-a","identity_b_id":"tenant-b"}'
    );
    expect(() => comparisonPayload('tenant-a', 'tenant-a')).toThrow('distinct');
  });

  it('summarizes normalized and structural similarity', () => {
    const diff = {
      normalized_similarity: 0.984,
      json: { structural_similarity: 1 }
    } as ResponseDiff;
    expect(comparisonSummary(diff)).toBe('98% normalized similarity · 100% JSON structure');
  });
});
