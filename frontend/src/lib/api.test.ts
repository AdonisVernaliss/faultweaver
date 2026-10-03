import { describe, expect, it } from 'vitest';

import { apiPath } from './api';

describe('apiPath', () => {
  it('normalizes API paths', () => {
    expect(apiPath('health')).toBe('/api/health');
    expect(apiPath('/health')).toBe('/api/health');
  });
});
