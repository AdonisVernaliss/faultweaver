<script lang="ts">
  import { api } from '../api';
  import type { AttackChain, AttackChainStep, Evidence, Finding } from '../types';

  let {
    engagementId, chains, findings, evidence, focusId, onchanged, onfinding
  }: {
    engagementId: string; chains: AttackChain[]; findings: Finding[]; evidence: Evidence[];
    focusId: string; onchanged: () => Promise<void>; onfinding: (id: string) => void;
  } = $props();

  let selectedId = $state('');
  let selectedStepId = $state('');
  let search = $state('');
  let statusFilter = $state('Active');
  let findingFilter = $state('');
  let createTitle = $state('');
  let title = $state('');
  let description = $state('');
  let resultingImpact = $state('');
  let findingId = $state('');
  let findingPosition = $state(1);
  let intermediateTitle = $state('');
  let intermediateDescription = $state('');
  let intermediatePosition = $state(1);
  let chainEvidenceId = $state('');
  let stepEvidenceId = $state('');
  let stepTitle = $state('');
  let stepDescription = $state('');
  let loadedId = $state('');
  let loadedStepId = $state('');
  let busy = $state(false);
  let error = $state('');

  $effect(() => {
    if (focusId) {
      selectedId = focusId;
      if (chains.find((item) => item.id === focusId)?.status === 'Archived') statusFilter = 'Archived';
    }
  });
  let filtered = $derived(chains.filter((item) => {
    const needle = search.trim().toLowerCase();
    const statusMatches = statusFilter === 'All' || (statusFilter === 'Active' ? item.status !== 'Archived' : item.status === statusFilter);
    return statusMatches && (!findingFilter || item.steps.some((step) => step.finding_id === findingFilter)) && (!needle || item.title.toLowerCase().includes(needle) || item.display_id.toLowerCase().includes(needle));
  }));
  let selected = $derived(filtered.find((item) => item.id === selectedId) ?? filtered[0]);
  let selectedStep = $derived(selected?.steps.find((item) => item.id === selectedStepId));

  $effect(() => {
    if (selected && selected.id !== loadedId) {
      loadedId = selected.id; title = selected.title; description = selected.description;
      resultingImpact = selected.resulting_impact; findingPosition = selected.steps.length + 1;
      intermediatePosition = selected.steps.length + 1; selectedStepId = selected.steps[0]?.id ?? '';
    } else if (selected && !selected.steps.some((item) => item.id === selectedStepId)) {
      selectedStepId = selected.steps[0]?.id ?? '';
    }
  });
  $effect(() => {
    if (selectedStep && selectedStep.id !== loadedStepId) {
      loadedStepId = selectedStep.id; stepTitle = selectedStep.title;
      stepDescription = selectedStep.description;
    }
  });

  async function createChain() {
    if (!createTitle.trim()) return;
    await run(async () => {
      const item = await api<AttackChain>(`engagements/${engagementId}/attack-chains`, { method: 'POST', body: JSON.stringify({ title: createTitle }) });
      createTitle = ''; selectedId = item.id; await onchanged();
    });
  }

  async function saveOverview() {
    if (!selected) return;
    await mutate(`engagements/${engagementId}/attack-chains/${selected.id}`, 'PATCH', { title, description, resulting_impact: resultingImpact });
  }

  async function addFinding() {
    if (!selected || !findingId) return;
    await mutate(`engagements/${engagementId}/attack-chains/${selected.id}/steps`, 'POST', { step_type: 'Finding', finding_id: findingId, position: findingPosition });
    findingId = '';
  }

  async function addIntermediate() {
    if (!selected || !intermediateTitle.trim()) return;
    await mutate(`engagements/${engagementId}/attack-chains/${selected.id}/steps`, 'POST', { step_type: 'Intermediate', title: intermediateTitle, description: intermediateDescription, position: intermediatePosition });
    intermediateTitle = ''; intermediateDescription = '';
  }

  async function moveStep(step: AttackChainStep, direction: -1 | 1) {
    if (!selected) return;
    const ids = selected.steps.map((item) => item.id);
    const from = ids.indexOf(step.id); const to = from + direction;
    if (to < 0 || to >= ids.length) return;
    [ids[from], ids[to]] = [ids[to], ids[from]];
    await mutate(`engagements/${engagementId}/attack-chains/${selected.id}/steps/order`, 'PUT', { ordered_step_ids: ids });
  }

  async function removeStep(step: AttackChainStep) {
    if (!selected) return;
    await mutate(`engagements/${engagementId}/attack-chains/${selected.id}/steps/${step.id}`, 'DELETE');
  }

  async function saveStep() {
    if (!selected || !selectedStep) return;
    await mutate(`engagements/${engagementId}/attack-chains/${selected.id}/steps/${selectedStep.id}`, 'PATCH', { title: stepTitle, description: stepDescription });
  }

  async function attachChainEvidence() {
    if (!selected || !chainEvidenceId) return;
    await mutate(`engagements/${engagementId}/attack-chains/${selected.id}/evidence`, 'POST', { evidence_id: chainEvidenceId });
    chainEvidenceId = '';
  }

  async function attachStepEvidence() {
    if (!selected || !selectedStep || !stepEvidenceId) return;
    await mutate(`engagements/${engagementId}/attack-chains/${selected.id}/steps/${selectedStep.id}/evidence`, 'POST', { evidence_id: stepEvidenceId });
    stepEvidenceId = '';
  }

  async function validateChain() {
    if (!selected) return;
    await mutate(`engagements/${engagementId}/attack-chains/${selected.id}`, 'PATCH', { status: 'Validated' });
  }

  async function archiveChain() {
    if (!selected) return;
    await mutate(`engagements/${engagementId}/attack-chains/${selected.id}`, 'DELETE');
  }

  async function mutate(path: string, method: string, body?: Record<string, unknown>) {
    await run(async () => {
      await api<AttackChain | void>(path, { method, body: body ? JSON.stringify(body) : undefined });
      await onchanged();
    });
  }

  async function run(action: () => Promise<void>) {
    busy = true; error = '';
    try { await action(); }
    catch (cause) { error = cause instanceof Error ? cause.message : 'Attack chain action failed'; }
    finally { busy = false; }
  }

  function composition(chain: AttackChain): string {
    const order = ['Critical', 'High', 'Medium', 'Low', 'Informational'];
    return order.filter((level) => chain.severity_composition[level]).map((level) => `${chain.severity_composition[level]} ${level}`).join(' · ') || 'No findings';
  }
</script>

<section class="workspace-page chain-page" aria-labelledby="chain-title">
  <header class="workspace-header"><div><span class="eyebrow">COMPOSED ATTACK PATHS</span><h1 id="chain-title">Attack Chains</h1><p>Operator-authored sequences of confirmed findings and verified intermediate steps.</p></div><div class="chain-create"><label><span>New chain title</span><input bind:value={createTitle} placeholder="Cross-Tenant Account Compromise" /></label><button class="button primary" type="button" onclick={createChain} disabled={busy || !createTitle.trim()}>Create Attack Chain</button></div></header>
  <div class="filter-bar"><label><span>Search</span><input bind:value={search} placeholder="ID or title" /></label><label><span>Status</span><select bind:value={statusFilter}><option>Active</option><option>All</option><option>Draft</option><option>Validated</option><option>Archived</option></select></label><label><span>Finding</span><select bind:value={findingFilter}><option value="">All findings</option>{#each findings as finding}<option value={finding.id}>{finding.display_id} {finding.title}</option>{/each}</select></label></div>
  <div class="chain-workspace">
    <aside class="record-list chain-list">{#each filtered as chain}<button class:active={selected?.id === chain.id} type="button" onclick={() => (selectedId = chain.id)}><span class="record-id">{chain.display_id}</span><strong>{chain.title}</strong><small>{chain.status} · {chain.steps.length} steps · {chain.finding_count} findings</small><em>{composition(chain)}</em><span class="retest-label">Updated {new Date(chain.updated_at).toLocaleString()}</span></button>{:else}<div class="empty-workspace"><span class="empty-glyph">⌁</span><strong>No attack chains</strong><p>Create an operator-authored path from existing confirmed findings.</p></div>{/each}</aside>
    {#if selected}
      <article class="chain-detail">
        <header class="report-heading"><div><span class="eyebrow">{selected.display_id}</span><h2>{selected.title}</h2><code>{selected.status} · {composition(selected)}</code></div><div class="heading-actions">{#if selected.status !== 'Archived'}<button class="button primary" type="button" onclick={validateChain} disabled={busy || selected.status === 'Validated'}>{selected.status === 'Validated' ? 'Validated' : 'Validate Chain'}</button><button class="button ghost" type="button" onclick={archiveChain} disabled={busy}>Archive</button>{/if}</div></header>
        <div class="chain-grid">
          <div class="chain-main">
            <section class="chain-overview"><label><span>Title</span><input bind:value={title} disabled={selected.status === 'Archived'} /></label><label><span>Description</span><textarea bind:value={description} rows="4" disabled={selected.status === 'Archived'}></textarea></label><label><span>Resulting Impact</span><textarea bind:value={resultingImpact} rows="6" placeholder="Describe the operator-reviewed business impact" disabled={selected.status === 'Archived'}></textarea></label>{#if selected.status !== 'Archived'}<button class="button secondary" type="button" onclick={saveOverview} disabled={busy}>Save chain narrative</button>{/if}</section>
            <section class="attack-path" aria-labelledby="attack-path-title"><div class="section-heading"><div><span class="eyebrow">ORDERED AND DIRECTED</span><h3 id="attack-path-title">Attack Path</h3></div><strong>{selected.steps.length} steps</strong></div><ol>{#each selected.steps as step, index}<li class:finding-step={step.step_type === 'Finding'} class:selected={selectedStep?.id === step.id}><button type="button" aria-label={`Select step ${step.position}: ${step.title}`} onclick={() => (selectedStepId = step.id)}><span class="step-index">{String(step.position).padStart(2, '0')}</span><div><small>{step.step_type === 'Finding' ? `${step.finding?.display_id} · ${step.finding?.severity}` : 'INTERMEDIATE STEP'}</small><strong>{step.title}</strong><p>{step.description || (step.step_type === 'Finding' ? step.finding?.status : 'Operator-authored transition')}</p></div><em>{step.evidence.length} EV</em></button>{#if selected.status !== 'Archived'}<div class="step-actions"><button type="button" aria-label={`Move ${step.title} up`} onclick={() => moveStep(step, -1)} disabled={index === 0 || busy}>↑</button><button type="button" aria-label={`Move ${step.title} down`} onclick={() => moveStep(step, 1)} disabled={index === selected.steps.length - 1 || busy}>↓</button><button type="button" aria-label={`Remove ${step.title}`} onclick={() => removeStep(step)} disabled={busy}>×</button></div>{/if}</li>{:else}<li class="empty-path"><strong>No steps yet</strong><p>Add a confirmed finding or an operator-authored intermediate step.</p></li>{/each}</ol></section>
            {#if selected.status !== 'Archived'}<section class="chain-builder"><div><h3>Add Finding</h3><label><span>Confirmed finding</span><select bind:value={findingId}><option value="">Select finding</option>{#each findings as finding}<option value={finding.id}>{finding.display_id} · {finding.title}</option>{/each}</select></label><label><span>Insert at position</span><input type="number" min="1" max={selected.steps.length + 1} bind:value={findingPosition} /></label><button class="button secondary" type="button" onclick={addFinding} disabled={busy || !findingId}>Add Finding</button></div><div><h3>Add Intermediate Step</h3><label><span>Step title</span><input bind:value={intermediateTitle} placeholder="Authenticated session obtained" /></label><label><span>Description</span><textarea bind:value={intermediateDescription} rows="3"></textarea></label><label><span>Insert at position</span><input type="number" min="1" max={selected.steps.length + 1} bind:value={intermediatePosition} /></label><button class="button secondary" type="button" onclick={addIntermediate} disabled={busy || !intermediateTitle.trim()}>Add Intermediate Step</button></div></section>{/if}
          </div>
          <aside class="chain-inspector">
            <section><span class="eyebrow">SELECTED STEP</span>{#if selectedStep}<h3>{selectedStep.title}</h3>{#if selectedStep.finding}<button class="text-action" type="button" onclick={() => onfinding(selectedStep.finding!.id)}>Open {selectedStep.finding.display_id} finding →</button>{/if}{#if selectedStep.step_type === 'Intermediate' && selected.status !== 'Archived'}<label><span>Title</span><input bind:value={stepTitle} /></label><label><span>Description</span><textarea bind:value={stepDescription} rows="4"></textarea></label><button class="button secondary" type="button" onclick={saveStep} disabled={busy}>Save step</button>{/if}<div class="attached-list">{#each selectedStep.evidence as item}<span><code>{item.display_id}</code>{item.title}</span>{:else}<p>No step evidence.</p>{/each}</div>{#if selected.status !== 'Archived'}<label><span>Attach Evidence to step</span><select bind:value={stepEvidenceId}><option value="">Select evidence</option>{#each evidence as item}<option value={item.id}>{item.display_id} · {item.title}</option>{/each}</select></label><button class="button secondary" type="button" onclick={attachStepEvidence} disabled={busy || !stepEvidenceId}>Attach to Step</button>{/if}{:else}<p>Select a path node to inspect it.</p>{/if}</section>
            <section><span class="eyebrow">CHAIN EVIDENCE</span><div class="attached-list">{#each selected.evidence as item}<span><code>{item.display_id}</code>{item.title}</span>{:else}<p>No chain-level evidence.</p>{/each}</div>{#if selected.status !== 'Archived'}<label><span>Attach Evidence to chain</span><select bind:value={chainEvidenceId}><option value="">Select evidence</option>{#each evidence as item}<option value={item.id}>{item.display_id} · {item.title}</option>{/each}</select></label><button class="button secondary" type="button" onclick={attachChainEvidence} disabled={busy || !chainEvidenceId}>Attach to Chain</button>{/if}</section>
            <section><span class="eyebrow">LIFECYCLE HISTORY</span><div class="timeline">{#each selected.history as item}<div class="timeline-item"><strong>{item.summary}</strong><time>{new Date(item.created_at).toLocaleString()}</time></div>{/each}</div></section>
          </aside>
        </div>
        {#if error}<p class="form-error" role="alert">{error}</p>{/if}
      </article>
    {:else}<div class="detail-placeholder">Create or select an attack chain.</div>{/if}
  </div>
</section>
