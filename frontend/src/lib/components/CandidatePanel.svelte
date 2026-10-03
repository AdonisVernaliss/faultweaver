<script lang="ts">
  import { api } from '../api';
  import type { Candidate } from '../types';

  let { engagementId, candidates, onchanged }: { engagementId: string; candidates: Candidate[]; onchanged: () => Promise<void> } = $props();
  let busy = $state(false);

  async function setStatus(candidate: Candidate, status: Candidate['status']) {
    busy = true;
    try {
      await api<Candidate>(`engagements/${engagementId}/candidates/${candidate.id}`, { method: 'PATCH', body: JSON.stringify({ status }) });
      await onchanged();
    } finally {
      busy = false;
    }
  }
</script>

<section class="workspace-page" aria-labelledby="candidate-title">
  <header class="workspace-header"><div><span class="eyebrow">REVIEW QUEUE</span><h1 id="candidate-title">Candidates</h1><p>Conservative signals only. Faultweaver never confirms authorization findings automatically.</p></div></header>
  <div class="candidate-list">
    {#each candidates as candidate}
      <article class="candidate-card"><header><div><span class="candidate-pill candidate">{candidate.confidence.toUpperCase()} CONFIDENCE</span><h2>{candidate.title}</h2></div><select value={candidate.status} disabled={busy} onchange={(event) => setStatus(candidate, event.currentTarget.value as Candidate['status'])}><option value="candidate">Candidate</option><option value="confirmed">Confirmed manually</option><option value="rejected">Rejected</option></select></header><div class="candidate-meta"><span>Comparison <code>{candidate.comparison_id.slice(0, 8)}</code></span><span>{candidate.supporting_replay_ids.length} evidence replays</span><span>{candidate.status}</span></div>{#each candidate.reasoning as reason}<p>{reason}</p>{/each}</article>
    {:else}<div class="empty-workspace"><span class="empty-glyph">◇</span><strong>No candidates</strong><p>Differential replay creates candidates only when strong authorization-inconsistency signals survive conservative checks.</p></div>{/each}
  </div>
</section>
