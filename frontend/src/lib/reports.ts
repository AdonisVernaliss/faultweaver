import { api, apiPath, ApiError } from './api';
import type { Finding, AttackChain } from './types';

export interface ReportContent {
  title: string;
  executive_summary: string;
  methodology: string;
  limitations: string;
  conclusion: string;
  finding_ids: string[] | null;
  attack_chain_ids: string[] | null;
  include_informational: boolean;
  include_archived: boolean;
  include_draft_chains: boolean;
  include_retest_history: boolean;
}
export interface ReportSummary {
  id: string; display_id: string; title: string;
  status: 'Draft' | 'Ready' | 'Generated' | 'Archived';
  version: number; revision_count: number; updated_at: string; generated_at: string | null;
}
export interface Report extends ReportSummary, ReportContent {}
export interface ReportRevision {
  revision: number; generated_at: string; schema_version: string; document_sha256: string;
}
export interface ReportReview {
  report: { title: string; revision: number | null };
  summary: { finding_count: number; attack_chain_count: number; retested_findings: number; severity: Record<string, number> };
  warnings: string[];
  retests: { display_id: string; finding_id: string; status: string; latest: boolean }[];
  scope: { scheme: string; host: string; port: number; path_prefix: string; active: boolean }[];
}
export interface ReportOptions {
  findings: (Pick<Finding, 'id' | 'display_id' | 'title' | 'severity' | 'status' | 'archived_at'> & { gaps: string[] })[];
  attack_chains: Pick<AttackChain, 'id' | 'display_id' | 'title' | 'status'>[];
}

export function reportForm(report: Report): ReportContent {
  return {
    title: report.title, executive_summary: report.executive_summary,
    methodology: report.methodology, limitations: report.limitations, conclusion: report.conclusion,
    finding_ids: report.finding_ids ? [...report.finding_ids] : null,
    attack_chain_ids: report.attack_chain_ids ? [...report.attack_chain_ids] : null,
    include_informational: report.include_informational, include_archived: report.include_archived,
    include_draft_chains: report.include_draft_chains, include_retest_history: report.include_retest_history
  };
}

export function eligibleFindings<T extends Pick<Finding, 'severity' | 'archived_at'>>(items: T[], form: ReportContent): T[] {
  return items.filter(f => (form.include_archived || !f.archived_at) && (form.include_informational || f.severity !== 'Informational'));
}
export function eligibleChains<T extends Pick<AttackChain, 'status'>>(items: T[], form: ReportContent): T[] {
  return items.filter(c => (form.include_archived || c.status !== 'Archived') && (form.include_draft_chains || c.status !== 'Draft'));
}
export function toggleIncluded(ids: string[] | null, available: string[], id: string, checked: boolean): string[] {
  const next = new Set(ids ?? available);
  if (checked) next.add(id); else next.delete(id);
  return [...next];
}
export function findingGaps(finding: Finding): string[] {
  return [!finding.description && 'Description', !finding.impact && 'Impact',
    !finding.reproduction_steps.length && 'Reproduction steps', !finding.remediation && 'Remediation',
    !finding.evidence_ids.length && 'Evidence'].filter((item): item is string => Boolean(item));
}
export const reportBase = (engagementId: string) => `engagements/${encodeURIComponent(engagementId)}/reports`;
export const reportPath = (engagementId: string, reportId: string) => `${reportBase(engagementId)}/${encodeURIComponent(reportId)}`;

export function saveReport(engagementId: string, report: Report, form: ReportContent, status?: 'Draft' | 'Ready' | 'Archived') {
  return api<Report>(reportPath(engagementId, report.id), {
    method: 'PATCH', body: JSON.stringify({ ...form, version: report.version, ...(status ? { status } : {}) })
  });
}
export function generateReport(engagementId: string, report: Report) {
  return api<ReportRevision>(`${reportPath(engagementId, report.id)}/generate`, {
    method: 'POST', body: JSON.stringify({ version: report.version })
  });
}
export function exportPath(engagementId: string, reportId: string, revision: number, format: 'html' | 'md' | 'json') {
  return apiPath(`${reportPath(engagementId, reportId)}/revisions/${revision}/export/${format}`);
}
export async function previewHTML(engagementId: string, reportId: string): Promise<string> {
  const response = await fetch(apiPath(`${reportPath(engagementId, reportId)}/preview/html`));
  if (!response.ok) throw new ApiError('Could not render the report preview; reload and retry', response.status);
  return response.text();
}
