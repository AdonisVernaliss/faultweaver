<script lang="ts">
  import { onMount } from 'svelte';

  import { assessmentIsActive, assessmentProgress, loadAssessment, stopAssessment } from '../assessments';
  import type { AssessmentDetail, AssessmentRun } from '../types';

  let {
    engagementId,
    runs,
    focusId = '',
    onnew,
    onchanged,
    onrequest,
    oncandidate
  }: {
    engagementId: string;
    runs: AssessmentRun[];
    focusId?: string;
    onnew: () => void;
    onchanged: () => Promise<void>;
    onrequest: (id: string) => void;
    oncandidate: (id: string) => void;
  } = $props();

  type Tab = 'overview' | 'surface' | 'requests' | 'observations' | 'candidates' | 'warnings' | 'configuration';
  let selectedId = $state('');
  let detail = $state<AssessmentDetail | null>(null);
  let tab = $state<Tab>('overview');
  let loading = $state(false);
  let stopping = $state(false);
  let error = $state('');
  let terminalSynced = $state('');

  $effect(() => {
    const target = focusId || selectedId || runs[0]?.id;
    if (target && target !== selectedId) void selectRun(target);
  });

  onMount(() => {
    const timer = window.setInterval(() => {
      if (detail && assessmentIsActive(detail)) void refreshDetail(true);
    }, 800);
    return () => window.clearInterval(timer);
  });

  async function selectRun(id: string) {
    selectedId = id;
    tab = 'overview';
    await refreshDetail(false);
  }

  async function refreshDetail(quiet: boolean) {
    if (!selectedId) return;
    if (!quiet) loading = true;
    error = '';
    try {
      const next = await loadAssessment(engagementId, selectedId);
      detail = next;
      if (!assessmentIsActive(next) && terminalSynced !== next.id) {
        terminalSynced = next.id;
        await onchanged();
      }
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not load the assessment';
    } finally {
      loading = false;
    }
  }

  async function stop() {
    if (!detail) return;
    stopping = true;
    error = '';
    try {
      await stopAssessment(engagementId, detail.id);
      await refreshDetail(true);
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not stop the assessment';
    } finally {
      stopping = false;
    }
  }

  function severityCount(severity: string): number {
    return detail?.observations.filter((item) => item.classification === 'Candidate' && item.suggested_severity === severity).length ?? 0;
  }
</script>

<section class="workspace-page assessment-page" aria-labelledby="assessment-title">
  <header class="workspace-header"><div><span class="eyebrow">AUTHORIZED BASELINE</span><h1 id="assessment-title">Assessment Runs</h1><p>Bounded discovery and passive analysis. Candidates always require manual verification.</p></div><button class="button primary" type="button" onclick={onnew}>＋ New Baseline</button></header>

  <div class="assessment-workspace">
    <aside class="record-list assessment-run-list" aria-label="Assessment runs">
      {#each runs as run}
        <button class:active={selectedId === run.id} type="button" onclick={() => selectRun(run.id)}>
          <span class="record-id">{run.display_id}</span><strong>{run.target_url}</strong><small>{assessmentProgress(run)}</small><em class:running={assessmentIsActive(run)}>{run.status}</em>
        </button>
      {:else}<div class="empty-workspace"><span class="empty-glyph">⌾</span><strong>No baseline runs</strong><p>Start with one exact in-scope HTTP or HTTPS target.</p></div>{/each}
    </aside>

    {#if loading}<div class="detail-placeholder"><span class="spinner"></span>Loading assessment…</div>
    {:else if detail}
      <article class="assessment-detail">
        <header class="assessment-heading"><div><span class="eyebrow">{detail.display_id} · {detail.status}</span><h2>{detail.target_url}</h2><p>{assessmentProgress(detail)}</p></div>{#if assessmentIsActive(detail)}<button class="button ghost danger" type="button" onclick={stop} disabled={stopping || detail.stop_requested}>{stopping || detail.stop_requested ? 'Stopping…' : 'Stop gracefully'}</button>{/if}</header>
        <div class="assessment-counters"><span><small>REQUESTS</small><strong>{detail.request_count}/{detail.max_requests}</strong></span><span><small>PAGES</small><strong>{detail.page_count}/{detail.max_pages}</strong></span><span><small>ENDPOINTS</small><strong>{detail.endpoint_count}</strong></span><span><small>OBSERVATIONS</small><strong>{detail.observation_count}</strong></span><span><small>CANDIDATES</small><strong>{detail.candidate_count}</strong></span><span><small>FAILED</small><strong>{detail.failed_request_count}</strong></span></div>
        {#if detail.status === 'Running'}<div class="live-progress" role="status"><i></i><strong>Running at depth {detail.current_depth}</strong><code>{detail.current_url ?? 'Preparing next request'}</code><span>{detail.queued_count} queued</span></div>{/if}
        <nav class="assessment-tabs" aria-label="Assessment detail sections">{#each ['overview', 'surface', 'requests', 'observations', 'candidates', 'warnings', 'configuration'] as item}<button class:active={tab === item} type="button" onclick={() => (tab = item as Tab)}>{item}</button>{/each}</nav>

        <div class="assessment-section">
          {#if tab === 'overview'}
            <div class="assessment-overview"><section><h3>Run status</h3><dl><div><dt>Started</dt><dd>{detail.started_at ? new Date(detail.started_at).toLocaleString() : 'Pending'}</dd></div><div><dt>Finished</dt><dd>{detail.finished_at ? new Date(detail.finished_at).toLocaleString() : '—'}</dd></div><div><dt>Stop reason</dt><dd>{detail.stop_reason ?? 'Natural frontier completion'}</dd></div></dl></section><section><h3>Candidate severity</h3><div class="severity-summary"><span><strong>{severityCount('High')}</strong>High</span><span><strong>{severityCount('Medium')}</strong>Medium</span><span><strong>{severityCount('Low')}</strong>Low</span><span><strong>{severityCount('Informational')}</strong>Info</span></div><p>Candidates require manual verification before promotion to findings.</p></section></div>
          {:else if tab === 'surface'}
            <div class="assessment-ledger"><h3>Discovered Surface</h3>{#each detail.discoveries as item}<article><code>{item.kind}</code><strong>{item.url}</strong><span>Depth {item.depth}</span><em class={item.state}>{item.state}{item.reason ? ` · ${item.reason}` : ''}</em></article>{:else}<p>No URLs discovered yet.</p>{/each}{#if detail.forms.length}<h3>Forms recorded — never submitted</h3>{#each detail.forms as form}<article><code>{form.method}</code><strong>{form.action_url}</strong><span>{form.fields.length} fields · {form.enctype}</span><button class="text-action" type="button" onclick={() => onrequest(form.exchange_id)}>Source request</button></article>{/each}{/if}</div>
          {:else if tab === 'requests'}
            <div class="assessment-ledger"><h3>Request Explorer evidence</h3><p>This run reuses the canonical HTTP exchange store. Open a request for headers, body, timing, replay, and evidence controls.</p>{#each detail.request_ids as id, index}<article><code>{String(index + 1).padStart(3, '0')}</code><strong>{id}</strong><span>Captured crawler exchange</span><button class="button ghost" type="button" onclick={() => onrequest(id)}>Open in Request Explorer</button></article>{:else}<p>No request has completed yet.</p>{/each}</div>
          {:else if tab === 'observations'}
            <div class="assessment-ledger"><h3>Passive Observations</h3>{#each detail.observations as item}<article><code>{item.classification}</code><strong>{item.title}<small>{item.check_id}</small></strong><span>{item.reason} · {item.occurrence_count} occurrence{item.occurrence_count === 1 ? '' : 's'}</span><em>{item.confidence} confidence</em></article>{:else}<p>No passive observations yet.</p>{/each}</div>
          {:else if tab === 'candidates'}
            <div class="assessment-ledger"><h3>Conservative Candidates</h3><p>These signals are hypotheses, not confirmed findings. Review supporting requests manually.</p>{#each detail.observations.filter((item) => item.candidate_id) as item}<article><code>{item.suggested_severity}</code><strong>{item.title}<small>{item.check_id}</small></strong><span>{item.reason}</span><button class="button ghost" type="button" onclick={() => item.candidate_id && oncandidate(item.candidate_id)}>Review candidate</button></article>{:else}<p>No candidate-level signals were generated.</p>{/each}</div>
          {:else if tab === 'warnings'}
            <div class="assessment-ledger"><h3>Warnings</h3>{#each detail.warnings as warning}<article><code>WARN</code><strong>{warning}</strong></article>{:else}<p>No warnings were recorded.</p>{/each}</div>
          {:else}
            <div class="configuration-grid"><span><small>TARGET</small><strong>{detail.target_url}</strong></span><span><small>MAX PAGES</small><strong>{detail.max_pages}</strong></span><span><small>MAX DEPTH</small><strong>{detail.max_depth}</strong></span><span><small>MAX REQUESTS</small><strong>{detail.max_requests}</strong></span><span><small>RATE</small><strong>{detail.requests_per_second}/sec</strong></span><span><small>CONCURRENCY</small><strong>{detail.concurrency}</strong></span><span><small>TIMEOUT</small><strong>{detail.request_timeout_seconds}s</strong></span><span><small>CAPTURE</small><strong>{detail.max_response_bytes} bytes</strong></span><span><small>QUERY VARIANTS</small><strong>{detail.max_query_variants_per_path}/path</strong></span><span><small>SITE METADATA</small><strong>{detail.inspect_site_metadata ? 'Enabled' : 'Disabled'}</strong></span></div>
          {/if}
        </div>
        {#if error}<p class="form-error assessment-error" role="alert">{error}</p>{/if}
      </article>
    {:else}<div class="detail-placeholder">Select a run to inspect its persisted results.</div>{/if}
  </div>
</section>
