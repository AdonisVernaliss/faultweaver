import { describe, expect, it } from 'vitest';

import { formatDuration, requestTarget, sourceLabel } from './format';

describe('request formatting', () => {
  it('formats request targets without dangling query markers', () => {
    expect(requestTarget('/api/projects', '')).toBe('/api/projects');
    expect(requestTarget('/api/projects', 'state=open')).toBe('/api/projects?state=open');
  });

  it('formats transport metadata', () => {
    expect(formatDuration(null)).toBe('—');
    expect(formatDuration(12.6)).toBe('13 ms');
    expect(sourceLabel('raw_import')).toBe('RAW HTTP');
    expect(sourceLabel('curl')).toBe('cURL');
  });
});
