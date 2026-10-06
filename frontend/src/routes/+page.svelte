<script lang="ts">
  import { onMount } from 'svelte';

  import { api } from '../lib/api';
  import { createRequestPageLoader, mergeRequestPages } from '../lib/request-browser';
  import AssessmentPanel from '../lib/components/AssessmentPanel.svelte';
  import AttackChainPanel from '../lib/components/AttackChainPanel.svelte';
  import AttackSurfacePanel from '../lib/components/AttackSurfacePanel.svelte';
  import AuthorizationMatrix from '../lib/components/AuthorizationMatrix.svelte';
  import CandidatePanel from '../lib/components/CandidatePanel.svelte';
  import ComparisonDialog from '../lib/components/ComparisonDialog.svelte';
  import CreateEngagementDialog from '../lib/components/CreateEngagementDialog.svelte';
  import EvidencePanel from '../lib/components/EvidencePanel.svelte';
  import FindingPanel from '../lib/components/FindingPanel.svelte';
  import IdentityPanel from '../lib/components/IdentityPanel.svelte';
  import ImportDialog from '../lib/components/ImportDialog.svelte';
  import NewAssessmentDialog from '../lib/components/NewAssessmentDialog.svelte';
  import RequestExplorer from '../lib/components/RequestExplorer.svelte';
  import ReportPanel from '../lib/components/ReportPanel.svelte';
  import RetestPanel from '../lib/components/RetestPanel.svelte';
  import ScopeDialog from '../lib/components/ScopeDialog.svelte';
  import Sidebar from '../lib/components/Sidebar.svelte';
  import type {
    AttackChain,
    AttackSurfaceEndpoint,
    AssessmentRun,
    Engagement,
    EngagementDetail,
    AuthorizationMatrix as Matrix,
    CandidateSummary,
    Comparison,
    Evidence,
    EvidenceSummary,
    Exchange,
    ExchangeSummary,
    ExchangeDetail,
    ExchangeList,
    Identity,
    Finding,
    ImportBatch,
    ImportResult,
    Retest,
    ScopeRule
  } from '../lib/types';

  let engagements = $state<Engagement[]>([]);
  let engagement = $state<EngagementDetail | null>(null);
  let scopes = $state<ScopeRule[]>([]);
  let requests = $state<ExchangeSummary[]>([]);
  let requestCount = $state(0);
  let requestTotal = $state(0);
  let requestOffset = $state(0);
  let requestFilter = $state('');
  let requestSource = $state('');
  let loadingRequests = $state(false);
  const requestLoader = createRequestPageLoader();
  let filterTimer: ReturnType<typeof setTimeout> | undefined;
  let identities = $state<Identity[]>([]);
  let matrix = $state<Matrix>({ identities: [], rows: [] });
  let candidates = $state<CandidateSummary[]>([]);
  let findings = $state<Finding[]>([]);
  let evidence = $state<EvidenceSummary[]>([]);
  let retests = $state<Retest[]>([]);
  let attackChains = $state<AttackChain[]>([]);
  let attackSurface = $state<AttackSurfaceEndpoint[]>([]);
  let importBatches = $state<ImportBatch[]>([]);
  let assessments = $state<AssessmentRun[]>([]);
  let focusedFindingId = $state('');
  let focusedAttackChainId = $state('');
  let focusedAssessmentId = $state('');
  let focusedCandidateId = $state('');
  let selected = $state<ExchangeDetail | null>(null);
  let activeView = $state<'assessments' | 'requests' | 'attack-surface' | 'identities' | 'matrix' | 'candidates' | 'findings' | 'evidence' | 'retests' | 'attack-chains' | 'reports'>('assessments');
  let reportDirty = $state(false);
  let loading = $state(true);
  let loadingDetail = $state(false);
  let replaying = $state(false);
  let createDialog = $state(false);
  let scopeDialog = $state(false);
  let importDialog = $state(false);
  let comparisonDialog = $state(false);
  let assessmentDialog = $state(false);
  let error = $state('');
  let notice = $state('');

  onMount(() => {
    void loadInitialState();
  });

  async function loadInitialState() {
    loading = true;
    error = '';
    try {
      engagements = await api<Engagement[]>('engagements');
      if (engagements.length) {
        const remembered = localStorage.getItem('faultweaver.engagement');
        const initial = engagements.find((item) => item.id === remembered) ?? engagements[0];
        await selectEngagement(initial.id);
      } else {
        createDialog = true;
      }
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not load the local workspace';
    } finally {
      loading = false;
    }
  }

  async function selectEngagement(id: string) {
    if (reportDirty && !window.confirm('Discard unsaved report edits and switch Engagement?')) return;
    reportDirty = false;
    error = '';
    selected = null;
    clearTimeout(filterTimer);
    requestLoader.invalidate();
    requestFilter = '';
    requestSource = '';
    loadingRequests = false;
    try {
      const [detail, scopeRules, assessmentItems, traffic, surfaceItems, batchItems, identityContexts, authMatrix, candidateItems, findingItems, evidenceItems, retestItems, chainItems, archivedChainItems] = await Promise.all([
        api<EngagementDetail>(`engagements/${id}`),
        api<ScopeRule[]>(`engagements/${id}/scopes`),
        api<AssessmentRun[]>(`engagements/${id}/assessments`),
        api<ExchangeList>(`engagements/${id}/requests`),
        api<AttackSurfaceEndpoint[]>(`engagements/${id}/attack-surface`),
        api<ImportBatch[]>(`engagements/${id}/imports`),
        api<Identity[]>(`engagements/${id}/identities`),
        api<Matrix>(`engagements/${id}/authorization-matrix`),
        api<CandidateSummary[]>(`engagements/${id}/candidates`),
        api<Finding[]>(`engagements/${id}/findings`),
        api<EvidenceSummary[]>(`engagements/${id}/evidence`),
        api<Retest[]>(`engagements/${id}/retests`),
        api<AttackChain[]>(`engagements/${id}/attack-chains`),
        api<AttackChain[]>(`engagements/${id}/attack-chains?status=Archived`)
      ]);
      engagement = detail;
      scopes = scopeRules;
      assessments = assessmentItems;
      requests = traffic.items;
      requestCount = requestTotal = traffic.total;
      requestOffset = traffic.items.length;
      attackSurface = surfaceItems;
      importBatches = batchItems;
      identities = identityContexts;
      matrix = authMatrix;
      candidates = candidateItems;
      findings = findingItems;
      evidence = evidenceItems;
      retests = retestItems;
      attackChains = [...chainItems, ...archivedChainItems];
      localStorage.setItem('faultweaver.engagement', id);
      if (requests.length) await selectRequest(requests[0].id);
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not load the engagement';
    }
  }

  async function refreshRequests(selectId?: string, append = false) {
    if (!engagement) return;
    clearTimeout(filterTimer);
    loadingRequests = true;
    try {
      const traffic = await requestLoader.load(engagement.id, requestFilter, requestSource, append ? requestOffset : 0);
      if (!traffic) return;
      requests = append ? mergeRequestPages(requests, traffic.items) : traffic.items;
      requestOffset = (append ? requestOffset : 0) + traffic.items.length;
      requestTotal = traffic.total;
      requestCount = traffic.unfilteredTotal;
      loadingRequests = false;
      if (selectId) await selectRequest(selectId);
    } catch (cause) {
      loadingRequests = false;
      error = cause instanceof Error ? cause.message : 'Could not load requests';
    }
  }

  function changeRequestFilter(filter: string, source: string) {
    requestFilter = filter;
    requestSource = source;
    requestLoader.invalidate();
    clearTimeout(filterTimer);
    loadingRequests = true;
    requests = [];
    filterTimer = setTimeout(() => void refreshRequests(), 200);
  }

  async function refreshImports() {
    if (!engagement) return;
    [attackSurface, importBatches] = await Promise.all([
      api<AttackSurfaceEndpoint[]>(`engagements/${engagement.id}/attack-surface`),
      api<ImportBatch[]>(`engagements/${engagement.id}/imports`)
    ]);
  }

  async function refreshAssessments() {
    if (!engagement) return;
    assessments = await api<AssessmentRun[]>(`engagements/${engagement.id}/assessments`);
  }

  async function refreshAssessmentArtifacts() {
    await Promise.all([refreshAssessments(), refreshRequests(), refreshImports(), refreshAnalysis()]);
  }

  async function refreshIdentities() {
    if (!engagement) return;
    identities = await api<Identity[]>(`engagements/${engagement.id}/identities`);
  }

  async function refreshAnalysis() {
    if (!engagement) return;
    [matrix, candidates] = await Promise.all([
      api<Matrix>(`engagements/${engagement.id}/authorization-matrix`),
      api<CandidateSummary[]>(`engagements/${engagement.id}/candidates`)
    ]);
  }

  async function refreshLifecycle() {
    if (!engagement) return;
    [findings, evidence, retests] = await Promise.all([
      api<Finding[]>(`engagements/${engagement.id}/findings`),
      api<EvidenceSummary[]>(`engagements/${engagement.id}/evidence`),
      api<Retest[]>(`engagements/${engagement.id}/retests`)
    ]);
  }

  async function refreshAttackChains() {
    if (!engagement) return;
    const [active, archived] = await Promise.all([
      api<AttackChain[]>(`engagements/${engagement.id}/attack-chains`),
      api<AttackChain[]>(`engagements/${engagement.id}/attack-chains?status=Archived`)
    ]);
    attackChains = [...active, ...archived];
  }

  async function refreshChainsAndFindings() {
    await Promise.all([refreshAttackChains(), refreshLifecycle()]);
  }

  async function selectRequest(id: string) {
    loadingDetail = true;
    error = '';
    try {
      selected = await api<ExchangeDetail>(`requests/${id}`);
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not load the request';
    } finally {
      loadingDetail = false;
    }
  }

  async function replaySelected() {
    if (!selected) return;
    replaying = true;
    error = '';
    try {
      const replay = await api<Exchange>(`requests/${selected.id}/replay`, {
        method: 'POST',
        body: '{}'
      });
      await refreshRequests(replay.id);
      showNotice(`Replay completed with HTTP ${replay.response_status ?? '—'}`);
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Replay failed';
    } finally {
      replaying = false;
    }
  }

  function compared(_: Comparison) {
    void Promise.all([refreshRequests(), refreshAnalysis()]);
    showNotice('Comparison and replay evidence saved locally');
  }

  async function saveRequestEvidence() {
    if (!engagement || !selected) return;
    try {
      const item = await api<Evidence>(`engagements/${engagement.id}/evidence`, {
        method: 'POST',
        body: JSON.stringify({
          evidence_type: selected.source === 'replay' ? 'Replay' : 'HTTP Request/Response',
          title: `${selected.method} ${selected.path}`,
          source_exchange_id: selected.id
        })
      });
      savedEvidence(item);
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not save evidence';
    }
  }

  function savedEvidence(item: Evidence) {
    evidence = [item, ...evidence.filter((existing) => existing.id !== item.id)];
    showNotice(`${item.display_id} captured as immutable evidence`);
  }

  function promotedFinding(item: Finding) {
    focusedFindingId = item.id;
    findings = [item, ...findings.filter((existing) => existing.id !== item.id)];
    activeView = 'findings';
    void refreshLifecycle();
    showNotice(`${item.display_id} created from reviewed candidate`);
  }

  function openFinding(id: string) {
    focusedFindingId = id;
    activeView = 'findings';
  }

  function openAttackChain(id: string) {
    focusedAttackChainId = id;
    activeView = 'attack-chains';
  }

  function openCandidate(id: string) {
    focusedCandidateId = id;
    activeView = 'candidates';
  }

  function openAssessmentRequest(id: string) {
    activeView = 'requests';
    void selectRequest(id);
  }

  function openEvidence(id: string) {
    activeView = 'requests';
    void selectRequest(id);
  }

  function createdEngagement(created: Engagement) {
    engagements = [created, ...engagements];
    createDialog = false;
    void selectEngagement(created.id).then(() => (scopeDialog = true));
  }

  function createdScope(scope: ScopeRule) {
    scopes = [...scopes, scope];
    scopeDialog = false;
    showNotice('Authorized scope added');
  }

  async function createdAssessment(run: AssessmentRun) {
    focusedAssessmentId = run.id;
    assessments = [run, ...assessments.filter((item) => item.id !== run.id)];
    assessmentDialog = false;
    activeView = 'assessments';
    showNotice(`${run.display_id} started with bounded anonymous requests`);
  }

  async function importedTraffic(result: ImportResult | Exchange) {
    const selectId = 'batch' in result ? result.request_ids[0] : result.id;
    await Promise.all([refreshRequests(selectId), refreshImports()]);
    showNotice('batch' in result ? `${result.batch.display_id} imported without sending traffic` : 'Request imported without sending traffic');
  }

  function openImport() {
    importDialog = true;
  }

  function scopeUrl(scope: ScopeRule): string {
    const isDefaultPort =
      (scope.scheme === 'http' && scope.port === 80) ||
      (scope.scheme === 'https' && scope.port === 443);
    return `${scope.scheme}://${scope.hostname}${isDefaultPort ? '' : `:${scope.port}`}${scope.path_prefix}`;
  }

  function showNotice(message: string) {
    notice = message;
    window.setTimeout(() => {
      if (notice === message) notice = '';
    }, 3500);
  }
</script>

<svelte:head>
  <title>{engagement ? `${engagement.name} · Faultweaver` : 'Faultweaver'}</title>
  <meta name="description" content="Local-first Web/API penetration-testing workspace" />
</svelte:head>

<div class="app-shell">
  <Sidebar
    {engagement}
    {requestCount}
    assessmentCount={assessments.length}
    identityCount={identities.length}
    candidateCount={candidates.length}
    findingCount={findings.length}
    evidenceCount={evidence.length}
    retestCount={retests.length}
    attackChainCount={attackChains.filter((item) => item.status !== 'Archived').length}
    attackSurfaceCount={attackSurface.length}
    {activeView}
    onview={(view) => {
      if (view !== activeView && reportDirty && !window.confirm('Discard unsaved report edits and leave Report?')) return;
      if (view !== activeView) reportDirty = false;
      activeView = view;
    }}
    oncreate={() => (createDialog = true)}
  />

  <main class="main-workspace">
    <header class="topbar">
      <div class="mobile-brand">FW</div>
      {#if engagement}
        <label class="engagement-select">
          <span class="sr-only">Current engagement</span>
          <select value={engagement.id} onchange={async (event) => { const select = event.currentTarget; await selectEngagement(select.value); select.value = engagement?.id ?? ''; }}>
            {#each engagements as item}
              <option value={item.id}>{item.name}</option>
            {/each}
          </select>
        </label>
        <span class="status-pill"><i></i>{engagement.status}</span>
      {:else}
        <strong>Faultweaver workspace</strong>
      {/if}
      <div class="topbar-spacer"></div>
      <span class="safety-label">AUTHORIZED TARGETS ONLY</span>
      <button class="icon-button" type="button" aria-label="Workspace settings">⋮</button>
    </header>

    {#if error}
      <div class="error-banner" role="alert">
        <strong>Action failed</strong><span>{error}</span><button onclick={() => (error = '')}>×</button>
      </div>
    {/if}

    {#if loading}
      <div class="loading-screen">
        <span class="spinner"></span><strong>Opening local workspace</strong
        ><small>Reading engagement state from SQLite</small>
      </div>
    {:else if engagement}
      <section class:empty={scopes.length === 0} class="scope-strip" id="scope">
        <div class="scope-strip-title">
          <span class="scope-icon">⌾</span>
          <div>
            <small>AUTHORIZED SCOPE</small>
            <strong
              >{scopes.length
                ? `${scopes.length} active rule${scopes.length === 1 ? '' : 's'}`
                : 'No outbound traffic allowed'}</strong
            >
          </div>
        </div>
        {#if scopes.length}
          <div class="scope-chips">
            {#each scopes.slice(0, 3) as scope}<code>{scopeUrl(scope)}</code>{/each}
          </div>
        {:else}
          <p>Add an exact scheme, hostname, port, and path boundary before importing traffic.</p>
        {/if}
        <button class="button secondary" type="button" onclick={() => (scopeDialog = true)}>
          ＋ Add scope
        </button>
      </section>

      {#if activeView === 'assessments'}
        <AssessmentPanel engagementId={engagement.id} runs={assessments} focusId={focusedAssessmentId} onnew={() => (assessmentDialog = true)} onchanged={refreshAssessmentArtifacts} onrequest={openAssessmentRequest} oncandidate={openCandidate} />
      {:else if activeView === 'requests'}
        <RequestExplorer
          {requests}
          {selected}
          {loadingDetail}
          {replaying}
          {identities}
          total={requestTotal}
          filter={requestFilter}
          sourceFilter={requestSource}
          {loadingRequests}
          hasMore={requestOffset < requestTotal}
          onfilter={changeRequestFilter}
          onmore={() => void refreshRequests(undefined, true)}
          onselect={selectRequest}
          onreplay={replaySelected}
          oncompare={() => (comparisonDialog = true)}
          onsaveevidence={saveRequestEvidence}
          onimport={openImport}
        />
      {:else if activeView === 'attack-surface'}
        <AttackSurfacePanel endpoints={attackSurface} batches={importBatches} onimport={openImport} />
      {:else if activeView === 'identities'}
        <IdentityPanel engagementId={engagement.id} {identities} onchanged={refreshIdentities} />
      {:else if activeView === 'matrix'}
        <AuthorizationMatrix {matrix} onopen={openEvidence} />
      {:else if activeView === 'candidates'}
        <CandidatePanel engagementId={engagement.id} {candidates} focusId={focusedCandidateId} onchanged={refreshAnalysis} onpromoted={promotedFinding} onevidence={savedEvidence} />
      {:else if activeView === 'findings'}
        <FindingPanel engagementId={engagement.id} {findings} {evidence} {attackChains} focusId={focusedFindingId} onchanged={refreshLifecycle} onchainschanged={refreshChainsAndFindings} onevidence={savedEvidence} onopenchain={openAttackChain} />
      {:else if activeView === 'evidence'}
        <EvidencePanel engagementId={engagement.id} {evidence} {findings} />
      {:else if activeView === 'retests'}
        <RetestPanel {retests} {findings} onopen={openFinding} />
      {:else if activeView === 'reports'}
        {#key engagement.id}<ReportPanel engagementId={engagement.id} ondirty={(dirty) => (reportDirty = dirty)} />{/key}
      {:else}
        <AttackChainPanel engagementId={engagement.id} chains={attackChains} {findings} {evidence} focusId={focusedAttackChainId} onchanged={refreshChainsAndFindings} onfinding={openFinding} />
      {/if}
    {:else}
      <section class="first-run">
        <span class="eyebrow">LOCAL-FIRST ASSESSMENT WORKSPACE</span>
        <h1>Begin with an engagement.</h1>
        <p>Define the authorized boundary before Faultweaver stores or sends HTTP traffic.</p>
        <button class="button primary" type="button" onclick={() => (createDialog = true)}>
          Create engagement
        </button>
      </section>
    {/if}
  </main>
</div>

{#if notice}<div class="toast" role="status"><span>✓</span>{notice}</div>{/if}

{#if createDialog}
  <CreateEngagementDialog
    onclose={() => (createDialog = false)}
    oncreated={createdEngagement}
  />
{/if}
{#if scopeDialog && engagement}
  <ScopeDialog
    engagementId={engagement.id}
    onclose={() => (scopeDialog = false)}
    oncreated={createdScope}
  />
{/if}
{#if importDialog && engagement}
  <ImportDialog
    engagementId={engagement.id}
    initialBaseUrl={scopes[0] ? scopeUrl(scopes[0]) : 'https://example.test/'}
    onclose={() => (importDialog = false)}
    onimported={importedTraffic}
  />
{/if}
{#if comparisonDialog && selected}
  <ComparisonDialog
    request={selected}
    {identities}
    onclose={() => (comparisonDialog = false)}
    oncompared={compared}
    onevidence={savedEvidence}
  />
{/if}
{#if assessmentDialog && engagement}
  <NewAssessmentDialog engagementId={engagement.id} initialTarget={scopes[0] ? scopeUrl(scopes[0]) : 'https://example.test/'} onclose={() => (assessmentDialog = false)} oncreated={createdAssessment} />
{/if}
