<script lang="ts">
  import { sourceLabel } from '../format';
  import type { AttackSurfaceEndpoint, ImportBatch } from '../types';

  let {
    endpoints,
    batches,
    onimport
  }: {
    endpoints: AttackSurfaceEndpoint[];
    batches: ImportBatch[];
    onimport: () => void;
  } = $props();

  let search = $state('');
  let stateFilter = $state('');
  let sourceFilter = $state('');
  let selectedId = $state('');
  let filtered = $derived(endpoints.filter((endpoint) => {
    const needle = search.trim().toLowerCase();
    return (!needle || endpoint.path_template.toLowerCase().includes(needle) || (endpoint.host ?? '').toLowerCase().includes(needle) || endpoint.method.toLowerCase().includes(needle)) &&
      (!stateFilter || endpoint.state === stateFilter) &&
      (!sourceFilter || endpoint.sources.includes(sourceFilter));
  }));
  let selected = $derived(filtered.find((endpoint) => endpoint.id === selectedId) ?? filtered[0]);

  function stateLabel(state: AttackSurfaceEndpoint['state']): string {
    return {
      observed_only: 'Observed only',
      declared_only: 'Declared only',
      observed_and_declared: 'Observed + declared'
    }[state];
  }

  function origin(endpoint: AttackSurfaceEndpoint): string {
    if (!endpoint.host) return 'Server not declared';
    const defaultPort = (endpoint.scheme === 'https' && endpoint.port === 443) || (endpoint.scheme === 'http' && endpoint.port === 80);
    return `${endpoint.scheme}://${endpoint.host}${defaultPort || !endpoint.port ? '' : `:${endpoint.port}`}`;
  }
</script>

<section class="workspace-page surface-page" aria-labelledby="surface-title">
  <header class="workspace-header"><div><span class="eyebrow">NORMALIZED INVENTORY</span><h1 id="surface-title">Attack Surface</h1><p>Observed traffic and declared OpenAPI operations, grouped conservatively.</p></div><button class="button primary" type="button" onclick={onimport}>＋ Import Traffic</button></header>
  <div class="surface-summary"><span><small>ENDPOINTS</small><strong>{endpoints.length}</strong></span><span><small>OBSERVED</small><strong>{endpoints.filter((item) => item.observed_request_count > 0).length}</strong></span><span><small>DECLARED</small><strong>{endpoints.filter((item) => item.declared_by_openapi).length}</strong></span><span><small>IMPORT BATCHES</small><strong>{batches.length}</strong></span></div>
  <div class="filter-bar"><label><span>Search</span><input bind:value={search} placeholder="Method, host, or path" /></label><label><span>State</span><select bind:value={stateFilter}><option value="">All states</option><option value="observed_only">Observed only</option><option value="declared_only">Declared only</option><option value="observed_and_declared">Observed + declared</option></select></label><label><span>Source</span><select bind:value={sourceFilter}><option value="">All sources</option><option value="raw_import">Raw HTTP</option><option value="har">HAR</option><option value="curl">cURL</option><option value="openapi">OpenAPI</option></select></label></div>

  <div class="surface-workspace">
    <div class="surface-list" role="list" aria-label="Attack surface endpoints">
      <div class="surface-head" aria-hidden="true"><span>METHOD</span><span>ENDPOINT</span><span>STATE</span><span>OBSERVED</span></div>
      {#each filtered as endpoint}
        <button class:active={selected?.id === endpoint.id} type="button" onclick={() => (selectedId = endpoint.id)}><code>{endpoint.method}</code><span><strong>{endpoint.path_template}</strong><small>{origin(endpoint)}</small></span><em>{stateLabel(endpoint.state)}</em><b>{endpoint.observed_request_count}</b></button>
      {:else}<div class="empty-workspace"><span class="empty-glyph">⌗</span><strong>No matching endpoints</strong><p>Import HAR, cURL, OpenAPI, or Raw HTTP data to enrich this inventory.</p></div>{/each}
    </div>
    <aside class="surface-detail">
      {#if selected}
        <header><span class="eyebrow">{stateLabel(selected.state)}</span><h2><code>{selected.method}</code> {selected.path_template}</h2><p>{origin(selected)}</p></header>
        <section><h3>Sources</h3><div class="source-tags">{#each selected.sources as source}<span>{sourceLabel(source)}</span>{/each}</div><dl><div><dt>Observed requests</dt><dd>{selected.observed_request_count}</dd></div><div><dt>Declared by OpenAPI</dt><dd>{selected.declared_by_openapi ? 'Yes' : 'No'}</dd></div>{#if selected.metadata.operation_id}<div><dt>Operation ID</dt><dd>{selected.metadata.operation_id}</dd></div>{/if}</dl></section>
        {#if selected.metadata.security?.length}<section><h3>Authentication metadata</h3>{#each selected.metadata.security as item}<div class="surface-fact"><strong>{item.kind ?? 'Unknown'}</strong><span>{item.name}{item.location ? ` · ${item.location}` : ''}</span></div>{/each}</section>{/if}
        {#if selected.metadata.parameters?.length}<section><h3>Parameters</h3>{#each selected.metadata.parameters as item}<div class="surface-fact"><strong>{item.name ?? 'Unnamed'}</strong><span>{item.in ?? 'unknown'}{item.required ? ' · required' : ''}</span></div>{/each}</section>{/if}
        {#if selected.metadata.responses}<section><h3>Declared responses</h3>{#each Object.entries(selected.metadata.responses) as [status, response]}<div class="surface-fact"><strong>{status}</strong><span>{response.content_types?.join(', ') || 'No content type declared'}</span></div>{/each}</section>{/if}
      {:else}<div class="detail-placeholder">Select an endpoint to inspect its provenance.</div>{/if}
    </aside>
  </div>

  <section class="import-ledger" aria-labelledby="import-history-title"><div class="section-heading"><div><span class="eyebrow">PROVENANCE</span><h2 id="import-history-title">Import History</h2></div><strong>{batches.length} batches</strong></div>{#each batches as batch}<article><code>{batch.display_id}</code><span><strong>{batch.import_format.toUpperCase()} Import</strong><small>{batch.original_filename ?? 'Pasted content'} · {new Date(batch.created_at).toLocaleString()}</small></span><em>{batch.imported_count}/{batch.total_records} imported</em><b class:partial={batch.status === 'partial'}>{batch.status}</b></article>{:else}<div class="empty-copy">No batch imports yet.</div>{/each}</section>
</section>
