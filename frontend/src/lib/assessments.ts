import { api } from './api';
import type { AssessmentCreate, AssessmentDetail, AssessmentRun } from './types';

export const conservativeAssessmentDefaults: AssessmentCreate = {
  target_url: '',
  max_pages: 50,
  max_depth: 3,
  max_requests: 75,
  requests_per_second: 1,
  concurrency: 2,
  request_timeout_seconds: 10,
  max_response_bytes: 1_000_000,
  max_query_variants_per_path: 3,
  inspect_site_metadata: true
};

export function createAssessment(
  engagementId: string,
  configuration: AssessmentCreate
): Promise<AssessmentRun> {
  return api<AssessmentRun>(`engagements/${engagementId}/assessments`, {
    method: 'POST',
    body: JSON.stringify(configuration)
  });
}

export function loadAssessment(engagementId: string, runId: string): Promise<AssessmentDetail> {
  return api<AssessmentDetail>(`engagements/${engagementId}/assessments/${runId}`);
}

export function stopAssessment(engagementId: string, runId: string): Promise<AssessmentRun> {
  return api<AssessmentRun>(`engagements/${engagementId}/assessments/${runId}/stop`, {
    method: 'POST'
  });
}

export function assessmentIsActive(run: AssessmentRun): boolean {
  return run.status === 'Pending' || run.status === 'Running';
}

export function assessmentProgress(run: AssessmentRun): string {
  if (run.status === 'Pending') return 'Waiting to start';
  if (run.status === 'Running') {
    return `${run.request_count} requests · ${run.page_count} pages · ${run.queued_count} queued`;
  }
  return `${run.request_count} requests · ${run.observation_count} observations · ${run.candidate_count} candidates`;
}
