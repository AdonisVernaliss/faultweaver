import type { Comparison, ResponseDiff } from './types';

export function comparisonPayload(identityA: string, identityB: string): string {
  if (!identityA || !identityB || identityA === identityB) {
    throw new Error('Choose two distinct identities');
  }
  return JSON.stringify({ identity_a_id: identityA, identity_b_id: identityB });
}

export function comparisonSummary(diff: ResponseDiff): string {
  const similarity = Math.round(diff.normalized_similarity * 100);
  const structural = Math.round(diff.json.structural_similarity * 100);
  return `${similarity}% normalized similarity · ${structural}% JSON structure`;
}

export function rawResponse(side: Comparison['replay_a']): string {
  if (side.response_status === null) return 'No response was captured.';
  return [
    `HTTP/1.1 ${side.response_status}`,
    ...side.response_headers.map((header) => `${header.name}: ${header.value}`),
    '',
    side.response_body ?? ''
  ].join('\r\n');
}
