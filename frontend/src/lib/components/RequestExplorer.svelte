<script lang="ts">
  import { formatDuration, requestTarget, sourceLabel } from '../format';
  import type { Exchange, ExchangeDetail } from '../types';

  let {
    requests,
    selected,
    loadingDetail,
    replaying,
    onselect,
    onreplay,
    onimport
  }: {
    requests: Exchange[];
    selected: ExchangeDetail | null;
    loadingDetail: boolean;
    replaying: boolean;
    onselect: (id: string) => void;
    onreplay: () => void;
    onimport: () => void;
  } = $props();

  let filter = $state('');
  let detailTab = $state<'request' | 'response'>('request');
  let representation = $state<'raw' | 'headers'>('raw');

  let filtered = $derived(
    requests.filter((request) => {
      const needle = filter.trim().toLowerCase();
      return (
        !needle ||
        request.method.toLowerCase().includes(needle) ||
        request.host.toLowerCase().includes(needle) ||
        requestTarget(request.path, request.query).toLowerCase().includes(needle) ||
        String(request.response_status ?? '').includes(needle)
      );
    })
  );

  function rawResponse(exchange: ExchangeDetail): string {
    if (exchange.response_status === null) return 'No response has been captured yet.';
    const status = `HTTP/1.1 ${exchange.response_status}`;
    const headers = exchange.response_headers.map((header) => `${header.name}: ${header.value}`);
    return [status, ...headers, '', exchange.response_body ?? ''].join('\r\n');
  }
</script>

<section class="explorer" id="request-explorer" aria-labelledby="explorer-title">
  <header class="workspace-header">
    <div>
      <span class="eyebrow">HTTP TRAFFIC</span>
      <h1 id="explorer-title">Request Explorer</h1>
      <p>Inspect captured traffic, replay deliberately, and preserve response evidence.</p>
    </div>
    <button class="button primary" type="button" onclick={onimport}>＋ Import request</button>
  </header>

  <div class="explorer-toolbar">
    <label class="search-field">
      <span aria-hidden="true">⌕</span>
      <span class="sr-only">Filter requests</span>
      <input bind:value={filter} placeholder="Filter method, host, path, or status" />
      <kbd>⌘K</kbd>
    </label>
    <div class="toolbar-stats">
      <span><strong>{filtered.length}</strong> visible</span>
      <span><strong>{requests.filter((request) => request.source === 'replay').length}</strong> replays</span>
    </div>
  </div>

  <div class="split-workspace">
    <div class="request-list-pane">
      <div class="table-head" aria-hidden="true">
        <span>METHOD</span><span>REQUEST TARGET</span><span>STATUS</span><span>SOURCE</span>
      </div>
      <div class="request-rows">
        {#each filtered as request (request.id)}
          <button
            type="button"
            class:active={selected?.id === request.id}
            class="request-row"
            onclick={() => onselect(request.id)}
          >
            <span class:post={request.method === 'POST'} class="method-badge">{request.method}</span>
            <span class="target-cell"><strong>{requestTarget(request.path, request.query)}</strong><small>{request.host}</small></span>
            <span class:pending={request.response_status === null} class="status-code">
              {request.response_status ?? '—'}
            </span>
            <span class="source-label">{sourceLabel(request.source)}</span>
          </button>
        {:else}
          <div class="empty-table">
            <span class="empty-glyph">↗</span>
            <strong>{requests.length ? 'No matching requests' : 'No traffic imported'}</strong>
            <p>{requests.length ? 'Adjust the current filter.' : 'Import a scoped raw HTTP request to begin.'}</p>
            {#if !requests.length}
              <button class="button secondary" type="button" onclick={onimport}>Import first request</button>
            {/if}
          </div>
        {/each}
      </div>
    </div>

    <div class="detail-pane">
      {#if loadingDetail}
        <div class="detail-placeholder"><span class="spinner"></span>Loading request…</div>
      {:else if selected}
        <header class="detail-header">
          <div class="request-identity">
            <span class:post={selected.method === 'POST'} class="method-badge">{selected.method}</span>
            <div><strong>{requestTarget(selected.path, selected.query)}</strong><small>{selected.url}</small></div>
          </div>
          <button class="button replay" type="button" onclick={onreplay} disabled={replaying}>
            {replaying ? 'Replaying…' : '▶ Replay'}
          </button>
        </header>

        <div class="detail-metrics">
          <span><small>STATUS</small><strong>{selected.response_status ?? 'Not sent'}</strong></span>
          <span><small>DURATION</small><strong>{formatDuration(selected.response_elapsed_ms)}</strong></span>
          <span><small>IDENTITY</small><strong>anonymous</strong></span>
          <span><small>SOURCE</small><strong>{sourceLabel(selected.source)}</strong></span>
        </div>

        <div class="tab-strip">
          <button class:active={detailTab === 'request'} type="button" onclick={() => (detailTab = 'request')}>Request</button>
          <button class:active={detailTab === 'response'} type="button" onclick={() => (detailTab = 'response')}>Response</button>
          <div class="representation-switch">
            <button class:active={representation === 'raw'} type="button" onclick={() => (representation = 'raw')}>Raw</button>
            <button class:active={representation === 'headers'} type="button" onclick={() => (representation = 'headers')}>Headers</button>
          </div>
        </div>

        {#if representation === 'raw'}
          <pre class="http-view">{detailTab === 'request' ? selected.raw_request : rawResponse(selected)}</pre>
        {:else}
          <div class="header-grid">
            {#each detailTab === 'request' ? selected.request_headers : selected.response_headers as header}
              <code>{header.name}</code><span>{header.value}</span>
            {:else}
              <p>No headers captured.</p>
            {/each}
          </div>
        {/if}

        <footer class="detail-footer">
          <span>{selected.id.slice(0, 8)}</span>
          {#if selected.response_truncated}<strong>Response truncated at safety limit</strong>{/if}
          {#if selected.parent_exchange_id}<span>Replay of {selected.parent_exchange_id.slice(0, 8)}</span>{/if}
        </footer>
      {:else}
        <div class="detail-placeholder"><span class="empty-glyph">⌁</span>Select a request to inspect it.</div>
      {/if}
    </div>
  </div>
</section>
