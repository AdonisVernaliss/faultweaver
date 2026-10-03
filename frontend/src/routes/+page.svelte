<script lang="ts">
  import { onMount } from 'svelte';

  import { api } from '../lib/api';
  import CreateEngagementDialog from '../lib/components/CreateEngagementDialog.svelte';
  import ImportDialog from '../lib/components/ImportDialog.svelte';
  import RequestExplorer from '../lib/components/RequestExplorer.svelte';
  import ScopeDialog from '../lib/components/ScopeDialog.svelte';
  import Sidebar from '../lib/components/Sidebar.svelte';
  import type {
    Engagement,
    EngagementDetail,
    Exchange,
    ExchangeDetail,
    ExchangeList,
    ScopeRule
  } from '../lib/types';

  let engagements = $state<Engagement[]>([]);
  let engagement = $state<EngagementDetail | null>(null);
  let scopes = $state<ScopeRule[]>([]);
  let requests = $state<Exchange[]>([]);
  let selected = $state<ExchangeDetail | null>(null);
  let loading = $state(true);
  let loadingDetail = $state(false);
  let replaying = $state(false);
  let createDialog = $state(false);
  let scopeDialog = $state(false);
  let importDialog = $state(false);
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
    error = '';
    selected = null;
    try {
      const [detail, scopeRules, traffic] = await Promise.all([
        api<EngagementDetail>(`engagements/${id}`),
        api<ScopeRule[]>(`engagements/${id}/scopes`),
        api<ExchangeList>(`engagements/${id}/requests`)
      ]);
      engagement = detail;
      scopes = scopeRules;
      requests = traffic.items;
      localStorage.setItem('faultweaver.engagement', id);
      if (requests.length) await selectRequest(requests[0].id);
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not load the engagement';
    }
  }

  async function refreshRequests(selectId?: string) {
    if (!engagement) return;
    const traffic = await api<ExchangeList>(`engagements/${engagement.id}/requests`);
    requests = traffic.items;
    if (selectId) await selectRequest(selectId);
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

  function importedRequest(exchange: Exchange) {
    importDialog = false;
    void refreshRequests(exchange.id);
    showNotice('Request imported without sending traffic');
  }

  function openImport() {
    if (!scopes.length) {
      scopeDialog = true;
      return;
    }
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
  <Sidebar {engagement} requestCount={requests.length} oncreate={() => (createDialog = true)} />

  <main class="main-workspace">
    <header class="topbar">
      <div class="mobile-brand">FW</div>
      {#if engagement}
        <label class="engagement-select">
          <span class="sr-only">Current engagement</span>
          <select value={engagement.id} onchange={(event) => selectEngagement(event.currentTarget.value)}>
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

      <RequestExplorer
        {requests}
        {selected}
        {loadingDetail}
        {replaying}
        onselect={selectRequest}
        onreplay={replaySelected}
        onimport={openImport}
      />
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
{#if importDialog && engagement && scopes[0]}
  <ImportDialog
    engagementId={engagement.id}
    initialBaseUrl={scopeUrl(scopes[0])}
    onclose={() => (importDialog = false)}
    onimported={importedRequest}
  />
{/if}
