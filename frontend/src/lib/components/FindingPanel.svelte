<script lang="ts">
  import { api } from '../api';
  import type { Evidence, Finding, FindingStatus, Retest, RetestStatus, Severity } from '../types';

  let { engagementId, findings, evidence, focusId, onchanged, onevidence }: {
    engagementId: string; findings: Finding[]; evidence: Evidence[]; focusId: string;
    onchanged: () => Promise<void>; onevidence: (item: Evidence) => void;
  } = $props();
  let selectedId = $state('');
  let editing = $state(false);
  let severityFilter = $state('');
  let statusFilter = $state('');
  let retestFilter = $state('');
  let busy = $state(false);
  let error = $state('');
  let noteBody = $state('');
  let evidenceText = $state('');
  let retestStatus = $state<RetestStatus>('Fixed');
  let retestNotes = $state('');
  let retestEvidenceIds = $state<string[]>([]);

  $effect(() => { if (focusId) selectedId = focusId; });
  let filtered = $derived(findings.filter((item) =>
    (!severityFilter || item.severity === severityFilter) &&
    (!statusFilter || item.status === statusFilter) &&
    (!retestFilter || (retestFilter === 'Not Retested' ? !item.latest_retest : item.latest_retest?.status === retestFilter))
  ));
  let selected = $derived(findings.find((item) => item.id === selectedId) ?? filtered[0]);
  let findingEvidence = $derived(evidence.filter((item) => item.finding_id === selected?.id));
  let retestEvidence = $derived(new Set(selected?.retests.flatMap((item) => item.evidence_ids) ?? []));

  async function saveFinding(event: SubmitEvent) {
    event.preventDefault();
    if (!selected) return;
    const data = new FormData(event.currentTarget as HTMLFormElement);
    await run(async () => {
      await api<Finding>(`engagements/${engagementId}/findings/${selected.id}`, {
        method: 'PATCH', body: JSON.stringify({
          title: data.get('title'), category: data.get('category'), severity: data.get('severity') as Severity,
          status: data.get('status') as FindingStatus, affected_asset: data.get('asset'),
          affected_endpoints: String(data.get('endpoints') ?? '').split('\n').map((item) => item.trim()).filter(Boolean),
          description: data.get('description'), impact: data.get('impact'), remediation: data.get('remediation'),
          reproduction_steps: String(data.get('steps') ?? '').split('\n').map((item) => item.trim()).filter(Boolean),
          references: String(data.get('references') ?? '').split('\n').map((item) => item.trim()).filter(Boolean)
        })
      });
      editing = false;
      await onchanged();
    });
  }

  async function addNote() {
    if (!selected || !noteBody.trim()) return;
    await run(async () => {
      await api(`engagements/${engagementId}/notes`, { method: 'POST', body: JSON.stringify({ target_type: 'finding', target_id: selected.id, body: noteBody }) });
      noteBody = '';
      await onchanged();
    });
  }

  async function saveNoteEvidence() {
    if (!selected || !evidenceText.trim()) return;
    await run(async () => {
      const item = await api<Evidence>(`engagements/${engagementId}/evidence`, { method: 'POST', body: JSON.stringify({ evidence_type: 'Operator Note', title: `${selected.display_id} operator observation`, text: evidenceText, finding_id: selected.id }) });
      evidenceText = '';
      onevidence(item);
      await onchanged();
    });
  }

  async function saveOriginalComparison() {
    if (!selected?.supporting_comparison_id) return;
    await run(async () => {
      const item = await api<Evidence>(`engagements/${engagementId}/evidence`, {
        method: 'POST', body: JSON.stringify({
          evidence_type: 'Response Comparison', title: `${selected.display_id} original comparison`,
          source_comparison_id: selected.supporting_comparison_id,
          source_candidate_id: selected.candidate_id, finding_id: selected.id
        })
      });
      onevidence(item);
      await onchanged();
    });
  }

  async function createRetest() {
    if (!selected) return;
    await run(async () => {
      await api<Retest>(`engagements/${engagementId}/findings/${selected.id}/retests`, { method: 'POST', body: JSON.stringify({ status: retestStatus, operator_notes: retestNotes, evidence_ids: retestEvidenceIds }) });
      retestNotes = '';
      retestEvidenceIds = [];
      await onchanged();
    });
  }

  function toggleRetestEvidence(id: string) {
    retestEvidenceIds = retestEvidenceIds.includes(id) ? retestEvidenceIds.filter((item) => item !== id) : [...retestEvidenceIds, id];
  }

  async function run(action: () => Promise<void>) {
    busy = true; error = '';
    try { await action(); }
    catch (cause) { error = cause instanceof Error ? cause.message : 'Action failed'; }
    finally { busy = false; }
  }
</script>

<section class="workspace-page lifecycle-page" aria-labelledby="finding-title">
  <header class="workspace-header"><div><span class="eyebrow">VERIFIED ISSUES</span><h1 id="finding-title">Findings</h1><p>Operator-authored records with stable identifiers, evidence, retests, and lifecycle history.</p></div></header>
  <div class="filter-bar"><label><span>Severity</span><select bind:value={severityFilter}><option value="">All severities</option><option>Critical</option><option>High</option><option>Medium</option><option>Low</option><option>Informational</option></select></label><label><span>Status</span><select bind:value={statusFilter}><option value="">All statuses</option><option>Open</option><option>In Remediation</option><option>Ready for Retest</option><option>Fixed</option><option>Accepted Risk</option><option>Closed</option></select></label><label><span>Retest</span><select bind:value={retestFilter}><option value="">Any retest state</option><option>Not Retested</option><option>Still Vulnerable</option><option>Partially Fixed</option><option>Fixed</option><option>Unable to Retest</option></select></label></div>
  <div class="lifecycle-split">
    <aside class="record-list">{#each filtered as finding}<button class:active={selected?.id === finding.id} type="button" onclick={() => (selectedId = finding.id)}><span class="record-id">{finding.display_id}</span><strong>{finding.title}</strong><small>{finding.affected_asset || 'Asset not specified'}</small><em class="severity-{finding.severity.toLowerCase()}">{finding.severity} · {finding.status}</em><span class="retest-label">{finding.latest_retest ? `${finding.latest_retest.display_id}: ${finding.latest_retest.status}` : 'Not Retested'}</span></button>{:else}<div class="empty-workspace"><span class="empty-glyph">◆</span><strong>No findings</strong><p>Promote a reviewed candidate to create the first finding.</p></div>{/each}</aside>
    {#if selected}
      <article class="report-detail">
        <header class="report-heading"><div><span class="eyebrow">{selected.display_id} · {selected.category}</span><h2>{selected.title}</h2><code>{selected.affected_asset || 'Affected asset pending'}</code></div><div class="heading-actions"><span class="severity-badge severity-{selected.severity.toLowerCase()}">{selected.severity}</span><button class="button secondary" type="button" onclick={() => (editing = !editing)}>{editing ? 'Cancel edit' : 'Edit finding'}</button></div></header>
        {#if editing}
          <form class="report-form" onsubmit={saveFinding}><div class="field-grid two"><label><span>Title</span><input name="title" value={selected.title} required /></label><label><span>Category</span><input name="category" value={selected.category} required /></label><label><span>Severity</span><select name="severity" value={selected.severity}><option>Critical</option><option>High</option><option>Medium</option><option>Low</option><option>Informational</option></select></label><label><span>Status</span><select name="status" value={selected.status}><option>Open</option><option>In Remediation</option><option>Ready for Retest</option><option>Fixed</option><option>Accepted Risk</option><option>Closed</option></select></label></div><label><span>Affected asset</span><input name="asset" value={selected.affected_asset} /></label><label><span>Affected endpoints — one per line</span><textarea name="endpoints" rows="3" value={selected.affected_endpoints.join('\n')}></textarea></label><label><span>Description</span><textarea name="description" rows="7" value={selected.description}></textarea></label><label><span>Impact</span><textarea name="impact" rows="5" value={selected.impact}></textarea></label><label><span>Reproduction steps — ordered, one per line</span><textarea name="steps" rows="7" value={selected.reproduction_steps.join('\n')}></textarea></label><label><span>Remediation</span><textarea name="remediation" rows="5" value={selected.remediation}></textarea></label><label><span>References — one per line</span><textarea name="references" rows="3" value={selected.references.join('\n')}></textarea></label><button class="button primary" type="submit" disabled={busy}>Save finding</button></form>
        {:else}
          <div class="context-grid"><span><small>STATUS</small><strong>{selected.status}</strong></span><span><small>CONFIRMED</small><strong>{new Date(selected.confirmed_at).toLocaleDateString()}</strong></span><span><small>RETEST</small><strong>{selected.latest_retest?.status ?? 'Not Retested'}</strong></span><span><small>UPDATED</small><strong>{new Date(selected.updated_at).toLocaleString()}</strong></span></div>
          <section class="report-section"><h3>Description</h3><p class:empty-copy={!selected.description}>{selected.description || 'Awaiting operator-authored description.'}</p></section><section class="report-section"><h3>Impact</h3><p class:empty-copy={!selected.impact}>{selected.impact || 'Awaiting operator-authored impact.'}</p></section><section class="report-section"><h3>Reproduction</h3><ol>{#each selected.reproduction_steps as step}<li>{step}</li>{:else}<li class="empty-copy">No reproduction steps recorded.</li>{/each}</ol></section><section class="report-section"><h3>Remediation</h3><p class:empty-copy={!selected.remediation}>{selected.remediation || 'No remediation guidance authored yet.'}</p></section>
        {/if}

        <section class="report-section"><h3>Evidence</h3><div class="evidence-groups"><div><small>ORIGINAL EVIDENCE</small>{#each findingEvidence.filter((item) => !retestEvidence.has(item.id)) as item}<span><code>{item.display_id}</code>{item.title}</span>{:else}<p class="empty-copy">No original evidence linked.</p>{/each}</div><div><small>RETEST EVIDENCE</small>{#each findingEvidence.filter((item) => retestEvidence.has(item.id)) as item}<span><code>{item.display_id}</code>{item.title}</span>{:else}<p class="empty-copy">No retest evidence linked.</p>{/each}</div></div>{#if selected.supporting_comparison_id}<button class="button secondary" type="button" onclick={saveOriginalComparison} disabled={busy}>Save original comparison as evidence</button>{/if}<label><span>Capture operator note as immutable evidence</span><textarea bind:value={evidenceText} rows="3"></textarea></label><button class="button secondary" type="button" onclick={saveNoteEvidence} disabled={busy || !evidenceText.trim()}>Save as evidence</button></section>

        <section class="report-section retest-composer"><h3>Record retest</h3><div class="field-grid two"><label><span>Result</span><select bind:value={retestStatus}><option>Still Vulnerable</option><option>Partially Fixed</option><option>Fixed</option><option>Unable to Retest</option></select></label><label><span>Operator notes</span><textarea bind:value={retestNotes} rows="3"></textarea></label></div><fieldset><legend>Supporting retest evidence</legend>{#each findingEvidence as item}<label class="check-row"><input type="checkbox" checked={retestEvidenceIds.includes(item.id)} onchange={() => toggleRetestEvidence(item.id)} /><span><code>{item.display_id}</code> {item.title}</span></label>{:else}<p class="empty-copy">Capture evidence before recording this attempt.</p>{/each}</fieldset><button class="button primary" type="button" onclick={createRetest} disabled={busy}>Record retest</button>{#each selected.retests as retest}<div class="retest-card"><header><code>{retest.display_id}</code><strong>{retest.status}</strong><time>{new Date(retest.tested_at).toLocaleString()}</time></header><p>{retest.operator_notes || 'No operator notes.'}</p><small>{retest.evidence_ids.length} supporting evidence item(s)</small></div>{/each}</section>

        <section class="report-section"><h3>Operator notes</h3>{#each selected.notes as item}<div class="timeline-item"><strong>{item.author_label}</strong><time>{new Date(item.created_at).toLocaleString()}</time><p>{item.body}</p></div>{/each}<label><span>Add note</span><textarea bind:value={noteBody} rows="3"></textarea></label><button class="button secondary" type="button" onclick={addNote} disabled={busy || !noteBody.trim()}>Add operator note</button></section>
        <section class="report-section"><h3>Lifecycle history</h3><div class="timeline">{#each selected.history as item}<div class="timeline-item"><i></i><strong>{item.summary}</strong><time>{new Date(item.created_at).toLocaleString()}</time></div>{/each}</div></section>
        {#if error}<p class="form-error" role="alert">{error}</p>{/if}
      </article>
    {:else}<div class="detail-placeholder">Select a finding to inspect the report record.</div>{/if}
  </div>
</section>
