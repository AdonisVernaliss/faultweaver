import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  importFormatOptions,
  importTrafficDocument,
  previewTrafficDocument
} from './traffic-import';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('real traffic import client', () => {
  it('exposes every supported format in the expected order', () => {
    expect(importFormatOptions.map((item) => item.value)).toEqual([
      'raw',
      'har',
      'curl',
      'openapi'
    ]);
  });

  it.each([
    ['har', '{"log":{"entries":[]}}', 'capture.har'],
    ['curl', 'curl https://api.example.test/resource', null],
    ['openapi', 'openapi: 3.1.0\npaths: {}', 'openapi.yaml']
  ] as const)('requests a redacted %s preview', async (format, content, filename) => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          import_format: format,
          total_records: 1,
          accepted_count: 1,
          response_count: 0,
          skipped_count: 0,
          warnings: ['Synthetic warning'],
          requests: [],
          endpoints: []
        }),
        { status: 200, headers: { 'content-type': 'application/json' } }
      )
    );
    vi.stubGlobal('fetch', fetchMock);

    const preview = await previewTrafficDocument('eng-1', format, content, filename);

    expect(fetchMock).toHaveBeenCalledWith(
      `/api/engagements/eng-1/imports/${format}/preview`,
      expect.objectContaining({ method: 'POST' })
    );
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ content, filename });
    expect(preview.warnings).toEqual(['Synthetic warning']);
  });

  it('imports only after preview through the persistence endpoint', async () => {
    const result = {
      batch: {
        id: 'batch-1',
        engagement_id: 'eng-1',
        display_id: 'IMP-001',
        import_format: 'har',
        original_filename: 'capture.har',
        status: 'completed',
        total_records: 1,
        imported_count: 1,
        response_count: 1,
        skipped_count: 0,
        warning_count: 0,
        new_endpoint_count: 1,
        known_endpoint_count: 0,
        warnings: [],
        created_at: '2026-10-04T00:00:00Z'
      },
      request_ids: ['req-1'],
      endpoint_ids: ['endpoint-1']
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(result), { status: 201 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      importTrafficDocument('eng-1', 'har', '{"log":{"entries":[]}}', 'capture.har')
    ).resolves.toEqual(result);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/engagements/eng-1/imports/har',
      expect.objectContaining({ method: 'POST' })
    );
  });
});
