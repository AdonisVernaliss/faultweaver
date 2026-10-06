<script lang="ts">
  import { api } from '../api';
  import type { Candidate, CandidateSummary, Evidence, Finding, Severity } from '../types';

  let {
    engagementId,
    candidates,
    focusId = '',
    onchanged,
    onpromoted,
    onevidence
  }: {
    engagementId: string;
    candidates: CandidateSummary[];
    focusId?: string;
    onchanged: () => Promise<void>;
    onpromoted: (finding: Finding) => void;
    onevidence: (evidence: Evidence) => void;
  } = $props();

  let selectedId = $state('');
  let busy = $state(false);
  let error = $state('');
  let note = $state('');
  let severity = $state<Severity>('Medium');
  let description = $state('');
  let impact = $state('');
  let remediation = $state('');
  let reproduction = $state('');

  let selected = $derived(candidates.find((item) => item.id === selectedId) ?? candidates[0]);

  $effect(() => {
    if (focusId && focusId !== selectedId) selectedId = focusId;
  });

  async function review(decision: 'False Positive' | 'Informational' | 'Accepted') {
    if (!selected) return;
    await run(async () => {
      await api<Candidate>(`engagements/${engagementId}/candidates/${selected.id}/review`, {
        method: 'POST', body: JSON.stringify({ decision, note })
      });
      note = '';
      await onchanged();
    });
  }

  async function promote() {
    if (!selected) return;
    await run(async () => {
      const finding = await api<Finding>(`engagements/${engagementId}/candidates/${selected.id}/promote`, {
        method: 'POST',
        body: JSON.stringify({
          severity, affected_asset: selected.target.host,
          affected_endpoints: [selected.target.path], description, impact, remediation,
          reproduction_steps: reproduction.split('\n').map((item) => item.trim()).filter(Boolean)
        })
      });
      await onchanged();
      onpromoted(finding);
    });
  }

  async function saveEvidence() {
    if (!selected) return;
    await run(async () => {
      const evidence = await api<Evidence>(`engagements/${engagementId}/evidence`, {
        method: 'POST',
        body: JSON.stringify({
          evidence_type: selected.comparison_id ? 'Response Comparison' : 'HTTP Request/Response',
          title: selected.comparison_id ? `${selected.title} comparison` : `${selected.title} request`,
          source_comparison_id: selected.comparison_id,
          source_exchange_id: selected.comparison_id ? undefined : selected.original_exchange_id,
          source_candidate_id: selected.id,
          finding_id: selected.finding_id
        })
      });
      onevidence(evidence);
    });
  }

  async function run(action: () => Promise<void>) {
    busy = true;
    error = '';
    try { await action(); }
    catch (cause) { error = cause instanceof Error ? cause.message : 'Action failed'; }
    finally { busy = false; }
  }
</script>

<section class="workspace-page lifecycle-page" aria-labelledby="candidate-title">
  <header class="workspace-header"><div><span class="eyebrow">REVIEW QUEUE</span><h1 id="candidate-title">Candidates</h1><p>Review the full differential context. Only an operator can promote a candidate.</p></div></header>
  <div class="lifecycle-split">
    <aside class="record-list" aria-label="Candidate list">
      {#each candidates as candidate}
        <button class:active={selected?.id === candidate.id} type="button" onclick={() => (selectedId = candidate.id)}>
          <span class="record-id">{candidate.confidence.toUpperCase()}</span><strong>{candidate.title}</strong>
          <small>{candidate.target.method} {candidate.target.host}{candidate.target.path}</small><em>{candidate.review_decision ?? 'Awaiting review'}</em>
        </button>
      {:else}<div class="empty-workspace"><span class="empty-glyph">◇</span><strong>No candidates</strong><p>Differential replay creates candidates only when conservative signals survive.</p></div>{/each}
    </aside>

    {#if selected}
      <article class="report-detail">
        <header class="report-heading"><div><span class="eyebrow">{selected.category}</span><h2>{selected.title}</h2><code>{selected.target.method} {selected.target.host}{selected.target.path}</code></div><span class="candidate-pill candidate">{selected.review_decision ?? selected.status}</span></header>
        <div class="context-grid"><span><small>CONFIDENCE</small><strong>{selected.confidence}</strong></span><span><small>ORIGINAL</small><strong>{selected.original_exchange_id.slice(0, 8)}</strong></span><span><small>{selected.comparison_id ? 'COMPARISON' : 'CHECK'}</small><strong>{selected.comparison_id?.slice(0, 8) ?? selected.check_id ?? 'Baseline'}</strong></span><span><small>CREATED</small><strong>{new Date(selected.created_at).toLocaleString()}</strong></span></div>
        <section class="report-section"><h3>Reasoning</h3>{#each selected.reasoning as reason}<p>{reason}</p>{/each}</section>
        <section class="report-section"><h3>{selected.comparison_id ? 'Identity replay evidence' : 'Supporting request evidence'}</h3>{#if selected.comparison_id}<div class="replay-summary">{#each selected.response_statuses as response}<div><span>{selected.identities.find((identity) => identity.id === response.identity_id)?.name ?? 'Identity'}</span><strong>HTTP {response.status ?? '—'}</strong><code>{response.exchange_id.slice(0, 8)}</code></div>{/each}</div>{:else}<p>{selected.affected_exchange_ids.length} crawler request{selected.affected_exchange_ids.length === 1 ? '' : 's'} support this conservative signal. Suggested severity: {selected.suggested_severity ?? 'Not set'}.</p>{/if}<button class="button secondary" type="button" onclick={saveEvidence} disabled={busy}>Save {selected.comparison_id ? 'comparison' : 'request'} as evidence</button></section>
        {#if selected.operator_notes.length}<section class="report-section"><h3>Operator notes</h3>{#each selected.operator_notes as item}<div class="timeline-item"><strong>{item.author_label}</strong><time>{new Date(item.created_at).toLocaleString()}</time><p>{item.body}</p></div>{/each}</section>{/if}

        {#if selected.status !== 'promoted'}
          <section class="review-decision"><h3>Review decision</h3><label><span>Decision note</span><textarea bind:value={note} rows="3" placeholder="Record the operator rationale"></textarea></label><div class="decision-actions"><button class="button ghost" type="button" onclick={() => review('False Positive')} disabled={busy}>False Positive</button><button class="button ghost" type="button" onclick={() => review('Informational')} disabled={busy}>Informational</button><button class="button ghost" type="button" onclick={() => review('Accepted')} disabled={busy}>Accepted</button></div></section>
          <section class="promotion-form"><div><span class="eyebrow">PROMOTE TO FINDING</span><h3>Operator-authored finding</h3><p>Automated reasoning is not copied into report prose.</p></div><div class="field-grid two"><label><span>Severity</span><select bind:value={severity}><option>Critical</option><option>High</option><option>Medium</option><option>Low</option><option>Informational</option></select></label><label><span>Asset</span><input value={selected.target.host} disabled /></label></div><label><span>Description</span><textarea bind:value={description} rows="5"></textarea></label><label><span>Impact</span><textarea bind:value={impact} rows="4"></textarea></label><label><span>Reproduction steps — one per line</span><textarea bind:value={reproduction} rows="5"></textarea></label><label><span>Remediation</span><textarea bind:value={remediation} rows="4"></textarea></label>{#if error}<p class="form-error" role="alert">{error}</p>{/if}<button class="button primary" type="button" onclick={promote} disabled={busy}>{busy ? 'Saving…' : 'Confirm and create finding'}</button></section>
        {:else if selected.finding_id}<div class="linked-record">Promoted and retained as source context for finding <code>{selected.finding_id.slice(0, 8)}</code>.</div>{/if}
      </article>
    {:else}<div class="detail-placeholder">Select a candidate to begin review.</div>{/if}
  </div>
</section>
