<script lang="ts">
  import { comparisonPayload, comparisonSummary, rawResponse } from '../analysis';
  import { api } from '../api';
  import type { Comparison, Evidence, ExchangeDetail, Identity } from '../types';
  import DialogShell from './DialogShell.svelte';

  let {
    request,
    identities,
    onclose,
    oncompared,
    onevidence
  }: {
    request: ExchangeDetail;
    identities: Identity[];
    onclose: () => void;
    oncompared: (comparison: Comparison) => void;
    onevidence: (evidence: Evidence) => void;
  } = $props();

  let identityA = $state('');
  let identityB = $state('');
  let comparison = $state<Comparison | null>(null);
  let view = $state<'raw' | 'normalized' | 'diff'>('diff');
  let busy = $state(false);
  let error = $state('');
  let evidenceSaved = $state(false);

  $effect(() => {
    if (!identityA && identities[0]) identityA = identities[0].id;
    if (!identityB && identities[1]) identityB = identities[1].id;
  });

  function identityName(id: string): string {
    return identities.find((identity) => identity.id === id)?.name ?? id.slice(0, 8);
  }

  async function compare(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = '';
    try {
      comparison = await api<Comparison>(`requests/${request.id}/compare`, {
        method: 'POST',
        body: comparisonPayload(identityA, identityB)
      });
      oncompared(comparison);
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Comparison failed';
    } finally {
      busy = false;
    }
  }

  async function saveEvidence() {
    if (!comparison) return;
    busy = true;
    error = '';
    try {
      const evidence = await api<Evidence>(`engagements/${comparison.engagement_id}/evidence`, {
        method: 'POST',
        body: JSON.stringify({
          evidence_type: 'Response Comparison',
          title: `${request.method} ${request.path} identity comparison`,
          source_comparison_id: comparison.id,
          source_candidate_id: comparison.candidate?.id ?? null
        })
      });
      evidenceSaved = true;
      onevidence(evidence);
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not save evidence';
    } finally {
      busy = false;
    }
  }
</script>

<DialogShell eyebrow="DIFFERENTIAL REPLAY" title="Compare identity responses" wide {onclose}>
  {#if !comparison}
    <form class="stack-form" onsubmit={compare}>
      <p class="form-note">Faultweaver will replay the unchanged request once per identity, preserve both responses, and save an explainable comparison.</p>
      <div class="comparison-route"><span>{request.method}</span><code>{request.path}{request.query ? `?${request.query}` : ''}</code></div>
      <div class="field-grid two">
        <label><span>Identity A</span><select bind:value={identityA}>{#each identities as identity}<option value={identity.id}>{identity.name}</option>{/each}</select></label>
        <label><span>Identity B</span><select bind:value={identityB}>{#each identities as identity}<option value={identity.id}>{identity.name}</option>{/each}</select></label>
      </div>
      {#if error}<p class="form-error" role="alert">{error}</p>{/if}
      <div class="dialog-actions"><button class="button ghost" type="button" onclick={onclose}>Cancel</button><button class="button primary" type="submit" disabled={busy || identityA === identityB}>{busy ? 'Replaying both…' : 'Replay and save comparison'}</button></div>
    </form>
  {:else}
    <div class="comparison-result">
      <div class="comparison-summary">
        <div><span class="eyebrow">SAVED COMPARISON</span><strong>{comparisonSummary(comparison.result.diff)}</strong></div>
        <span class:candidate={comparison.candidate} class="candidate-pill">{comparison.candidate ? 'CANDIDATE' : 'NO CANDIDATE'}</span>
      </div>
      <div class="tab-strip compact-tabs">
        <button class:active={view === 'diff'} type="button" onclick={() => (view = 'diff')}>Structured diff</button>
        <button class:active={view === 'raw'} type="button" onclick={() => (view = 'raw')}>Raw responses</button>
        <button class:active={view === 'normalized'} type="button" onclick={() => (view = 'normalized')}>Normalized</button>
      </div>
      {#if view === 'diff'}
        <div class="diff-grid">
          <div><small>STATUS</small><strong>{comparison.result.diff.status.a} ↔ {comparison.result.diff.status.b}</strong></div>
          <div><small>CONTENT TYPE</small><strong>{comparison.result.diff.content_type.a ?? '—'} ↔ {comparison.result.diff.content_type.b ?? '—'}</strong></div>
          <div><small>BODY SIZE</small><strong>{comparison.result.diff.body_size.a} B ↔ {comparison.result.diff.body_size.b} B</strong></div>
          <div><small>JSON SHAPE</small><strong>{Math.round(comparison.result.diff.json.structural_similarity * 100)}%</strong></div>
        </div>
        <div class="field-diff-list">
          <section><span>ADDED</span>{#each comparison.result.diff.json.added_fields as field}<code>+ {field}</code>{:else}<small>None</small>{/each}</section>
          <section><span>REMOVED</span>{#each comparison.result.diff.json.removed_fields as field}<code>− {field}</code>{:else}<small>None</small>{/each}</section>
          <section><span>CHANGED</span>{#each comparison.result.diff.json.changed_fields as field}<code>{field.path}: {JSON.stringify(field.a)} → {JSON.stringify(field.b)}</code>{:else}<small>None</small>{/each}</section>
        </div>
        {#if comparison.candidate}<div class="candidate-note"><strong>{comparison.candidate.title}</strong>{#each comparison.candidate.reasoning as reason}<p>{reason}</p>{/each}</div>{/if}
      {:else}
        <div class="side-by-side">
          <section><header><span>A</span><strong>{identityName(comparison.identity_a_id)}</strong><em>HTTP {comparison.replay_a.response_status}</em></header><pre>{view === 'raw' ? rawResponse(comparison.replay_a) : JSON.stringify(comparison.result.normalized_a, null, 2)}</pre></section>
          <section><header><span>B</span><strong>{identityName(comparison.identity_b_id)}</strong><em>HTTP {comparison.replay_b.response_status}</em></header><pre>{view === 'raw' ? rawResponse(comparison.replay_b) : JSON.stringify(comparison.result.normalized_b, null, 2)}</pre></section>
        </div>
      {/if}
      {#if error}<p class="form-error" role="alert">{error}</p>{/if}
      <div class="dialog-actions"><button class="button secondary" type="button" onclick={saveEvidence} disabled={busy || evidenceSaved}>{evidenceSaved ? 'Saved as evidence' : 'Save comparison as evidence'}</button><button class="button primary" type="button" onclick={onclose}>Done</button></div>
    </div>
  {/if}
</DialogShell>
