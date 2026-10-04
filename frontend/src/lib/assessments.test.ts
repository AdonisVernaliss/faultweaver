import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  assessmentIsActive,
  assessmentProgress,
  conservativeAssessmentDefaults,
  createAssessment,
  loadAssessment,
  stopAssessment
} from './assessments';
import type { AssessmentRun } from './types';

afterEach(() => vi.unstubAllGlobals());

function run(status: AssessmentRun['status']): AssessmentRun {
  return {
    status,
    request_count: status === 'Running' ? 4 : 9,
    page_count: 3,
    queued_count: status === 'Running' ? 2 : 0,
    observation_count: 5,
    candidate_count: 2
  } as AssessmentRun;
}

describe('baseline assessment client', () => {
  it('uses conservative bounded defaults and concrete progress counters', () => {
    expect(conservativeAssessmentDefaults).toMatchObject({
      max_pages: 50,
      max_depth: 3,
      max_requests: 75,
      requests_per_second: 1,
      concurrency: 2
    });
    expect(assessmentIsActive(run('Pending'))).toBe(true);
    expect(assessmentIsActive(run('Running'))).toBe(true);
    expect(assessmentIsActive(run('Completed'))).toBe(false);
    expect(assessmentProgress(run('Running'))).toBe('4 requests · 3 pages · 2 queued');
    expect(assessmentProgress(run('Stopped'))).toBe(
      '9 requests · 5 observations · 2 candidates'
    );
  });

  it('creates, monitors, and stops runs through the assessment API', async () => {
    const responses = [run('Running'), run('Running'), run('Stopped')];
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify(responses.shift()), {
          status: 200,
          headers: { 'content-type': 'application/json' }
        })
      )
    );
    vi.stubGlobal('fetch', fetchMock);

    await createAssessment('eng-1', {
      ...conservativeAssessmentDefaults,
      target_url: 'https://example.test/'
    });
    await loadAssessment('eng-1', 'run-1');
    await stopAssessment('eng-1', 'run-1');

    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      '/api/engagements/eng-1/assessments',
      '/api/engagements/eng-1/assessments/run-1',
      '/api/engagements/eng-1/assessments/run-1/stop'
    ]);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST' });
    expect(fetchMock.mock.calls[2][1]).toMatchObject({ method: 'POST' });
  });
});
