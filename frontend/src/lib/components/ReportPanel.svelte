<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '../api';
  import { eligibleChains, eligibleFindings, exportPath, generateReport, previewHTML, reportBase,
    reportForm, reportPath, saveReport, toggleIncluded, type Report, type ReportContent,
    type ReportOptions, type ReportReview, type ReportRevision, type ReportSummary } from '../reports';

  let { engagementId, ondirty = () => {} }: { engagementId: string; ondirty?: (dirty: boolean) => void } = $props();
  const sections = ['Overview', 'Executive Summary', 'Scope & Methodology', 'Findings', 'Attack Chains', 'Retests', 'Preview / Export'];
  let reports = $state<ReportSummary[]>([]);
  let options = $state<ReportOptions>({ findings: [], attack_chains: [] });
  let selected = $state<Report | null>(null);
  let form = $state<ReportContent | null>(null);
  let review = $state<ReportReview | null>(null);
  let html = $state('');
  let revisions = $state<ReportRevision[]>([]);
  let exportRevision = $state(0);
  let section = $state('Overview');
  let loading = $state(true);
  let busy = $state(false);
  let error = $state('');
  let notice = $state('');
  let newTitle = $state('Web & API security assessment');
  let ticket = 0;
  const dirty = $derived(Boolean(selected && form && JSON.stringify(form) !== JSON.stringify(reportForm(selected))));
  const availableFindings = $derived(form ? eligibleFindings(options.findings, form) : []);
  const availableChains = $derived(form ? eligibleChains(options.attack_chains, form) : []);
  $effect(() => { ondirty(dirty); });

  onMount(() => {
    void initialize();
    return () => { ticket++; ondirty(false); };
  });

  function mayDiscard() { return !dirty || window.confirm('Discard unsaved report edits? Saved drafts and revisions will remain.'); }
  function beforeUnload(event: BeforeUnloadEvent) { if (dirty) { event.preventDefault(); event.returnValue = ''; } }
  function fail(cause: unknown) { error = cause instanceof Error ? cause.message : 'Could not update this report'; }

  async function initialize() {
    const epoch = ++ticket;
    loading = true;
    error = '';
    try {
      const [items, choices] = await Promise.all([
        api<ReportSummary[]>(`${reportBase(engagementId)}?include_archived=true`),
        api<ReportOptions>(`${reportBase(engagementId)}/options`)
      ]);
      if (epoch !== ticket) return;
      reports = items; options = choices;
      if (reports.length) await openReport(reports[0].id, false);
    } catch (cause) { if (epoch === ticket) fail(cause); }
    finally { loading = false; }
  }

  async function refreshList() {
    reports = await api<ReportSummary[]>(`${reportBase(engagementId)}?include_archived=true`);
  }

  async function openReport(id: string, guard = true) {
    if (guard && !mayDiscard()) return;
    const epoch = ++ticket;
    busy = true; error = ''; html = ''; review = null;
    try {
      const [item, history] = await Promise.all([
        api<Report>(reportPath(engagementId, id)),
        api<ReportRevision[]>(`${reportPath(engagementId, id)}/revisions`)
      ]);
      if (epoch !== ticket) return;
      selected = item; form = reportForm(item); revisions = history;
      exportRevision = history[0]?.revision ?? 0;
      await refreshPreview(id, epoch);
    } catch (cause) { if (epoch === ticket) fail(cause); }
    finally { if (epoch === ticket) busy = false; }
  }

  async function refreshPreview(id: string, epoch = ticket) {
    const [document, rendered] = await Promise.all([
      api<ReportReview>(`${reportPath(engagementId, id)}/preview`), previewHTML(engagementId, id)
    ]);
    if (epoch === ticket) { review = document; html = rendered; }
  }

  async function create() {
    if (!newTitle.trim() || !mayDiscard()) return;
    busy = true; error = ''; notice = '';
    try {
      const item = await api<Report>(reportBase(engagementId), { method: 'POST', body: JSON.stringify({ title: newTitle }) });
      await refreshList();
      await openReport(item.id, false);
      section = 'Overview';
    } catch (cause) { fail(cause); }
    finally { busy = false; }
  }

  async function save(status?: 'Draft' | 'Ready' | 'Archived', showPreview = false) {
    if (!selected || !form) return;
    busy = true; error = ''; notice = '';
    try {
      const item = selected.status === 'Archived'
        ? await api<Report>(reportPath(engagementId, selected.id), { method: 'PATCH', body: JSON.stringify({ version: selected.version, status: 'Draft' }) })
        : await saveReport(engagementId, selected, form, status);
      selected = item; form = reportForm(item);
      await Promise.all([refreshList(), refreshPreview(item.id)]);
      notice = status === 'Archived' ? 'Report archived. Generated revisions remain available.' : 'Report saved. Existing revisions are unchanged.';
      if (showPreview) section = 'Preview / Export';
    } catch (cause) { fail(cause); }
    finally { busy = false; }
  }

  async function generate() {
    if (!selected || dirty) return;
    busy = true; error = ''; notice = '';
    try {
      const revision = await generateReport(engagementId, selected);
      const id = selected.id;
      await refreshList(); await openReport(id, false);
      exportRevision = revision.revision;
      notice = `Revision ${revision.revision} preserved. Download the required format below.`;
    } catch (cause) { fail(cause); }
    finally { busy = false; }
  }
</script>

<svelte:window onbeforeunload={beforeUnload} />
<section class="workspace-page lifecycle-page report-workspace" aria-labelledby="report-title">
  <header class="workspace-header">
    <div><span class="eyebrow">ASSESSMENT DELIVERABLES</span><h1 id="report-title">Report</h1>
      <p>Compose the operator's conclusions, review confirmed findings, and preserve a shareable revision.</p></div>
  </header>
  {#if error}<div class="form-error" role="alert">{error} <button class="text-action" type="button" onclick={() => selected ? openReport(selected.id) : initialize()}>Reload saved state</button></div>{/if}
  {#if notice}<p class="report-notice" role="status">{notice}</p>{/if}
  {#if loading}<p role="status">Loading report workspace…</p>
  {:else}
    <div class="report-picker">
      <label>Saved reports<select value={selected?.id ?? ''} disabled={busy || !reports.length} onchange={(event) => { const select = event.currentTarget; void openReport(select.value).then(() => { select.value = selected?.id ?? ''; }); }}>
        {#if !reports.length}<option value="">No reports yet</option>{/if}
        {#each reports as item}<option value={item.id}>{item.display_id} · {item.title} · {item.status}</option>{/each}
      </select></label>
      <form onsubmit={(event) => { event.preventDefault(); void create(); }}>
        <label>New report title<input maxlength="200" required bind:value={newTitle} disabled={busy} /></label>
        <button class="button secondary" disabled={busy || !newTitle.trim()} type="submit">＋ Create draft</button>
      </form>
    </div>
    {#if selected && form}
      <div class="report-toolbar">
        <div><strong>{selected.display_id}</strong><span>{selected.status}</span><small role="status">{busy ? 'Updating report…' : dirty ? 'Unsaved edits' : 'Saved'}</small></div>
        <div class="report-actions">
          {#if selected.status === 'Archived'}<button class="button secondary" type="button" disabled={busy} onclick={() => save('Draft')}>Restore draft</button>
          {:else}
            <button class="button primary" type="button" disabled={busy || !form.title.trim()} onclick={() => save()}>Save draft</button>
            <button class="button secondary" type="button" disabled={busy} onclick={() => save('Ready')}>Mark ready</button>
            <button class="button ghost" type="button" disabled={busy} onclick={() => save('Archived')}>Archive report</button>
          {/if}
        </div>
      </div>
      <nav class="report-sections" aria-label="Report editor sections">
        {#each sections as label}<button type="button" class:active={section === label} aria-current={section === label ? 'page' : undefined} onclick={() => (section = label)}>{label}</button>{/each}
      </nav>
      <fieldset class="report-editor" disabled={busy || selected.status === 'Archived'}>
        <legend class="sr-only">Report content</legend>
        {#if section === 'Overview'}
          <label>Report title<input maxlength="200" required bind:value={form.title} /></label>
          <div class="report-metrics"><div><strong>{review?.summary.finding_count ?? '—'}</strong><span>Included Findings</span></div><div><strong>{review?.summary.attack_chain_count ?? '—'}</strong><span>Attack Chains</span></div><div><strong>{selected.revision_count}</strong><span>Preserved revisions</span></div></div>
          <p class="muted-copy">Counts and review notes reflect the saved draft. Severity is separate from Finding status; Fixed and Accepted Risk Findings remain Findings. Unconfirmed Candidates are never included.</p>
          {#if review?.warnings.length}<div class="report-review"><h2>Content review</h2><p>These notes do not prevent saving. Optional prose is never invented.</p><ul>{#each review.warnings as warning}<li>{warning}</li>{/each}</ul></div>{/if}
        {:else if section === 'Executive Summary'}
          <label>Executive Summary<textarea rows="10" maxlength="30000" bind:value={form.executive_summary} placeholder="Write the assessment's business interpretation in your own words."></textarea></label>
          <label>Conclusion<textarea rows="6" maxlength="30000" bind:value={form.conclusion} placeholder="Summarize the verified outcome and remaining work."></textarea></label>
          <p class="muted-copy">Plain text only. Findings counts do not automatically determine business conclusions.</p>
        {:else if section === 'Scope & Methodology'}
          <p class="muted-copy">Scope is taken from this Engagement's configured authorization rules at generation time. Discovered routes do not expand it.</p>
          <ul class="report-retests">{#each review?.scope ?? [] as rule}<li><code>{rule.scheme}://{rule.host}:{rule.port}{rule.path_prefix}</code><span>{rule.active ? 'Active scope' : 'Inactive rule'}</span></li>{:else}<li>No authorized scope configured. Add scope before generating a report.</li>{/each}</ul>
          <label>Methodology<textarea rows="8" maxlength="30000" bind:value={form.methodology} placeholder="Describe the methods actually used and manually verified."></textarea></label>
          <label>Assessment limitations<textarea rows="8" maxlength="30000" bind:value={form.limitations} placeholder="Record unavailable roles, excluded endpoints and other coverage limits."></textarea></label>
        {:else if section === 'Findings'}
          <div class="report-options"><label class="check-row"><input type="checkbox" bind:checked={form.include_informational} />Include Informational Findings</label><label class="check-row"><input type="checkbox" bind:checked={form.include_archived} />Allow archived Findings and chains</label></div>
          <button class="text-action" type="button" onclick={() => { if (form) form.finding_ids = null; }}>Use all eligible Findings</button>
          <div class="report-selection">{#each availableFindings as finding}<label><input type="checkbox" checked={form.finding_ids === null || form.finding_ids.includes(finding.id)} onchange={(event) => { if (form) form.finding_ids = toggleIncluded(form.finding_ids, availableFindings.map(f => f.id), finding.id, event.currentTarget.checked); }} />
            <span><strong>{finding.display_id} · {finding.title}</strong><small>{finding.severity} · {finding.status}{finding.archived_at ? ' · Archived' : ''}</small>{#if finding.gaps.length}<em>Review: {finding.gaps.join(', ')}</em>{/if}</span></label>{:else}<p>No eligible confirmed Findings. Confirm and promote reviewed Candidates in the Findings workflow first.</p>{/each}</div>
        {:else if section === 'Attack Chains'}
          <div class="report-options"><label class="check-row"><input type="checkbox" bind:checked={form.include_draft_chains} />Allow Draft Attack Chains</label><label class="check-row"><input type="checkbox" bind:checked={form.include_archived} />Allow archived Findings and chains</label></div>
          <p class="muted-copy">Validated chains are included by default when their Findings are selected. Explicit chain selection requires all of its Findings; no aggregate risk score is invented.</p>
          <button class="text-action" type="button" onclick={() => { if (form) form.attack_chain_ids = null; }}>Use eligible chains by default</button>
          <div class="report-selection">{#each availableChains as chain}<label><input type="checkbox" checked={form.attack_chain_ids === null || form.attack_chain_ids.includes(chain.id)} onchange={(event) => { if (form) form.attack_chain_ids = toggleIncluded(form.attack_chain_ids, availableChains.map(c => c.id), chain.id, event.currentTarget.checked); }} /><span><strong>{chain.display_id} · {chain.title}</strong><small>{chain.status}</small></span></label>{:else}<p>No eligible chains. Compose and validate an Attack Chain before including it.</p>{/each}</div>
        {:else if section === 'Retests'}
          <label class="check-row"><input type="checkbox" bind:checked={form.include_retest_history} />Include full retest history (otherwise latest result only)</label>
          <p class="muted-copy">Original immutable Evidence stays distinct from Retest Evidence. Findings that were never retested are not counted as retested.</p>
          <ul class="report-retests">{#each review?.retests ?? [] as retest}<li><strong>{retest.display_id} · {retest.finding_id}</strong><span>{retest.status} · {retest.latest ? 'Latest' : 'Historical'}</span></li>{:else}<li>No retests in the saved selection.</li>{/each}</ul>
        {:else}
          <p class="muted-copy">The preview reflects saved current sources. Generate a revision to freeze that content. Downloads use the selected immutable revision, even after later edits.</p>
          {#if dirty}<p role="status">Save edits before previewing or generating.</p><button class="button primary" type="button" onclick={() => save(undefined, true)}>Save and preview</button>
          {:else}<button class="button primary" type="button" onclick={generate}>Generate revision</button>{/if}
        {/if}
      </fieldset>
      {#if section === 'Preview / Export'}
        <div class="report-downloads">
          <label>Preserved revision<select bind:value={exportRevision} disabled={!revisions.length || busy}>{#if !revisions.length}<option value={0}>Generate a revision first</option>{/if}{#each revisions as revision}<option value={revision.revision}>Revision {revision.revision} · {new Date(revision.generated_at).toLocaleString()}</option>{/each}</select></label>
          {#if exportRevision}{#each ['html', 'md', 'json'] as format}<a class="button secondary" href={exportPath(engagementId, selected.id, exportRevision, format as 'html' | 'md' | 'json')} download>Download {format === 'md' ? 'Markdown' : format.toUpperCase()}</a>{/each}{/if}
        </div>
        <p class="muted-copy">Exports leave encrypted storage. Treat them as confidential deliverables and review them before sharing. HTML works offline and can be printed to PDF externally.</p>
        {#if html && !dirty}<iframe title="Saved draft report preview" sandbox="" srcdoc={html}></iframe>{/if}
      {/if}
    {:else}<div class="empty-workspace"><strong>No reports yet</strong><p>Create a draft above, write your conclusions, then review Findings and Evidence before export.</p></div>{/if}
  {/if}
</section>

<style>
  .report-workspace { max-width: 1500px; margin: auto; min-width: 0; }
  .report-picker { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr); gap: 1rem; margin-bottom: 1rem; }
  .report-picker form, .report-actions, .report-downloads { display: flex; flex-wrap: wrap; align-items: end; gap: .65rem; }
  .report-picker form label { flex: 1; }
  label { display: flex; flex-direction: column; gap: .5rem; min-width: 0; font-size: .8rem; color: var(--muted); }
  input:not([type=checkbox]), select, textarea { width: 100%; min-width: 0; padding: .7rem; border: 1px solid var(--border); background: var(--bg); color: var(--text); font: inherit; border-radius: 4px; }
  textarea { resize: vertical; line-height: 1.7; }
  .report-toolbar { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 1rem; padding: 1rem; border: 1px solid var(--border); background: var(--panel); }
  .report-toolbar > div:first-child { display: flex; align-items: center; flex-wrap: wrap; gap: .8rem; }
  .report-toolbar small, .muted-copy { color: var(--muted); line-height: 1.65; }
  .report-sections { display: flex; flex-wrap: wrap; gap: .3rem; padding: .8rem 0; }
  .report-sections button { padding: .65rem .8rem; border: 1px solid transparent; background: transparent; color: var(--muted); font-size: .78rem; }
  .report-sections button.active { color: var(--accent-bright); background: var(--accent-bg); border-color: var(--border); }
  .report-editor { display: grid; gap: 1.3rem; min-width: 0; margin: 0; padding: 1.3rem; border: 1px solid var(--border); background: var(--panel); }
  .report-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; }
  .report-metrics div { display: flex; flex-direction: column; padding: 1rem; background: var(--panel-raised); }
  .report-metrics strong { font-size: 1.7rem; }.report-metrics span { color: var(--muted); font-size: .76rem; }
  .report-review { border-left: 3px solid var(--warning); padding: .5rem 1rem; font-size: .8rem; }
  .report-review h2 { font-size: 1rem; }.report-review li { margin: .4rem 0; }
  .report-options { display: flex; flex-wrap: wrap; gap: 1.3rem; }.check-row { flex-direction: row; align-items: center; }
  .report-selection { display: grid; gap: .6rem; }.report-selection label { flex-direction: row; align-items: start; padding: 1rem; border: 1px solid var(--border); cursor: pointer; }
  .report-selection span { display: grid; gap: .4rem; min-width: 0; }.report-selection strong { color: var(--text); overflow-wrap: anywhere; }.report-selection em { color: var(--warning); font-style: normal; }
  input[type=checkbox] { accent-color: var(--accent); min-width: 16px; min-height: 16px; }
  .report-retests { list-style: none; padding: 0; }.report-retests li { display: flex; flex-wrap: wrap; justify-content: space-between; gap: .6rem; border-bottom: 1px solid var(--border); padding: .8rem 0; }
  .report-downloads { margin: 1.3rem 0; }.report-downloads label { flex: 1; min-width: min(260px, 100%); }
  iframe { display: block; width: 100%; height: 850px; border: 1px solid var(--border); background: white; }
  .report-notice { color: var(--accent-bright); font-size: .85rem; }
  :is(button, a, input, textarea, select):focus-visible { outline: 2px solid var(--accent-bright); outline-offset: 3px; }
  @media (max-width: 768px) { .report-picker { grid-template-columns: 1fr; }.report-editor { padding: .8rem; }.report-metrics { gap: .4rem; }.report-metrics div { padding: .7rem; }.report-metrics span { font-size: .67rem; }.report-sections button { flex: 1 1 130px; }.report-downloads { align-items: stretch; }.report-downloads a { flex: 1; text-align: center; }iframe { height: 700px; } }
</style>
