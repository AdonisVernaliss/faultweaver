<script lang="ts">
  import { conservativeAssessmentDefaults, createAssessment } from '../assessments';
  import type { AssessmentCreate, AssessmentRun } from '../types';
  import DialogShell from './DialogShell.svelte';

  let {
    engagementId,
    initialTarget,
    onclose,
    oncreated
  }: {
    engagementId: string;
    initialTarget: string;
    onclose: () => void;
    oncreated: (run: AssessmentRun) => void | Promise<void>;
  } = $props();

  let configuration = $state<AssessmentCreate>({
    ...conservativeAssessmentDefaults,
    target_url: ''
  });
  let busy = $state(false);
  let error = $state('');

  $effect(() => {
    if (!configuration.target_url) configuration.target_url = initialTarget;
  });

  async function start() {
    busy = true;
    error = '';
    try {
      const run = await createAssessment(engagementId, configuration);
      await oncreated(run);
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not start the assessment';
    } finally {
      busy = false;
    }
  }
</script>

<DialogShell eyebrow="BOUNDED PASSIVE BASELINE" title="New Assessment" wide {onclose}>
  <form class="stack-form" onsubmit={(event) => { event.preventDefault(); void start(); }}>
    <label><span>Authorized target URL</span><input bind:value={configuration.target_url} required type="url" spellcheck="false" /></label>
    <div class="field-grid three assessment-limits">
      <label><span>Maximum pages</span><input bind:value={configuration.max_pages} min="1" max="500" required type="number" /></label>
      <label><span>Maximum depth</span><input bind:value={configuration.max_depth} min="0" max="10" required type="number" /></label>
      <label><span>Total requests</span><input bind:value={configuration.max_requests} min="1" max="1000" required type="number" /></label>
      <label><span>Requests / second</span><input bind:value={configuration.requests_per_second} min="0.1" max="20" step="0.1" required type="number" /></label>
      <label><span>Concurrency</span><input bind:value={configuration.concurrency} min="1" max="8" required type="number" /></label>
      <label><span>Timeout, seconds</span><input bind:value={configuration.request_timeout_seconds} min="1" max="60" required type="number" /></label>
      <label><span>Response capture, bytes</span><input bind:value={configuration.max_response_bytes} min="1024" max="10000000" required type="number" /></label>
      <label><span>Query variants / path</span><input bind:value={configuration.max_query_variants_per_path} min="1" max="25" required type="number" /></label>
      <label class="check-row"><input bind:checked={configuration.inspect_site_metadata} type="checkbox" /><span>Inspect in-scope robots.txt and sitemap.xml</span></label>
    </div>
    <div class="safety-callout">
      <strong>Safe baseline behavior</strong>
      <p>Start sends only bounded anonymous GET requests. Forms are recorded but never submitted. JavaScript is not executed, and redirects are scope-checked before any follow-up request.</p>
    </div>
    {#if error}<p class="form-error" role="alert">{error}</p>{/if}
    <div class="dialog-actions"><button class="button ghost" type="button" onclick={onclose}>Cancel</button><button class="button primary" type="submit" disabled={busy || !configuration.target_url}>{busy ? 'Starting…' : 'Start baseline assessment'}</button></div>
  </form>
</DialogShell>
