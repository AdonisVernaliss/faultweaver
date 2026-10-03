import { describe, expect, it } from 'vitest';

import { filterRequests, formatDuration, requestTarget, sourceLabel } from './format';

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

  it('combines text and source filters without changing the request list', () => {
    const requests = [
      {
        method: 'GET',
        host: 'api.example.test',
        path: '/users',
        query: '',
        response_status: 200,
        source: 'har'
      },
      {
        method: 'POST',
        host: 'api.example.test',
        path: '/orders',
        query: 'state=open',
        response_status: null,
        source: 'curl'
      }
    ];

    expect(filterRequests(requests, 'orders', 'curl')).toEqual([requests[1]]);
    expect(filterRequests(requests, '', 'har')).toEqual([requests[0]]);
    expect(requests).toHaveLength(2);
  });
});
