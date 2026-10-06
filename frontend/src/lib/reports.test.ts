import { afterEach, describe, expect, it, vi } from 'vitest';
import reportComponent from './components/ReportPanel.svelte?raw';
import { eligibleChains, eligibleFindings, exportPath, findingGaps, generateReport, previewHTML,
  reportForm, saveReport, toggleIncluded, type Report } from './reports';
import type { AttackChain, Finding } from './types';

const report: Report = {
  id: 'report-1', display_id: 'REP-001', title: 'Synthetic assessment', status: 'Draft', version: 3,
  revision_count: 0, updated_at: '', generated_at: null, executive_summary: 'Operator interpretation',
  methodology: '', limitations: '', conclusion: '', finding_ids: null, attack_chain_ids: null,
  include_informational: true, include_archived: false, include_draft_chains: false, include_retest_history: true
};

describe('report workspace', () => {
  afterEach(() => vi.unstubAllGlobals());
  it('edits independent drafts without mutating the loaded report', () => {
    const form = reportForm(report);
    form.executive_summary = 'Reviewed interpretation';
    expect(report.executive_summary).toBe('Operator interpretation');
    expect('version' in form).toBe(false);
  });
  it('keeps defaults and explicit inclusion separate', () => {
    expect(toggleIncluded(null, ['f1', 'f2'], 'f2', false)).toEqual(['f1']);
    expect(toggleIncluded([], ['f1', 'f2'], 'f2', true)).toEqual(['f2']);
    const form = reportForm(report);
    const findings = [{ id: 'f1', severity: 'High', archived_at: null }, { id: 'f2', severity: 'Informational', archived_at: null },
      { id: 'f3', severity: 'Low', archived_at: 'date' }] as Finding[];
    expect(eligibleFindings(findings, form).map(f => f.id)).toEqual(['f1', 'f2']);
    form.include_informational = false;
    expect(eligibleFindings(findings, form).map(f => f.id)).toEqual(['f1']);
    const chains = [{ status: 'Validated' }, { status: 'Draft' }, { status: 'Archived' }] as AttackChain[];
    expect(eligibleChains(chains, form)).toHaveLength(1);
    form.include_draft_chains = true;
    expect(eligibleChains(chains, form)).toHaveLength(2);
  });
  it('identifies missing prose without manufacturing it', () => {
    const finding = { description: '', impact: 'Known impact', reproduction_steps: [], remediation: '', evidence_ids: [] } as unknown as Finding;
    expect(findingGaps(finding)).toEqual(['Description', 'Reproduction steps', 'Remediation', 'Evidence']);
  });
  it('saves versioned prose before explicitly generating a revision', async () => {
    const requests: [string, RequestInit | undefined][] = [];
    vi.stubGlobal('fetch', vi.fn(async (path, init) => {
      requests.push([String(path), init]);
      return Response.json(requests.length === 1 ? { ...report, version: 4 } : { revision: 1 });
    }));
    const saved = await saveReport('eng-1', report, { ...reportForm(report), executive_summary: 'Updated' });
    await generateReport('eng-1', saved);
    expect(JSON.parse(requests[0][1]!.body as string).executive_summary).toBe('Updated');
    expect(requests[0][1]!.method).toBe('PATCH');
    expect(JSON.parse(requests[1][1]!.body as string)).toEqual({ version: 4 });
    expect(requests[1][0]).toBe('/api/engagements/eng-1/reports/report-1/generate');
  });
  it('preserves safe preview errors and builds only revision download URLs', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('unavailable', { status: 503 })));
    await expect(previewHTML('eng', 'report')).rejects.toThrow('Could not render');
    expect(exportPath('eng', 'report', 2, 'html')).toBe('/api/engagements/eng/reports/report/revisions/2/export/html');
  });
  it('uses a sandboxed preview and responsive editor layout', () => {
    const component = reportComponent;
    expect(component).toContain('sandbox=""');
    expect(component).not.toContain('{@html');
    expect(component).toContain('@media (max-width: 768px)');
    expect(component).toContain('Executive Summary');
    expect(component).toContain('Generate revision');
  });
});
