<script lang="ts">
  import { api } from '../api';
  import {
    importFormatOptions,
    importWarningLabel,
    importTrafficDocument,
    previewTrafficDocument
  } from '../traffic-import';
  import type { Exchange, ImportFormat, ImportPreview, ImportResult } from '../types';
  import DialogShell from './DialogShell.svelte';

  let {
    engagementId,
    initialBaseUrl,
    onclose,
    onimported
  }: {
    engagementId: string;
    initialBaseUrl: string;
    onclose: () => void;
    onimported: (result: ImportResult | Exchange) => void | Promise<void>;
  } = $props();

  function initialRawForm() {
    const initialUrl = new URL(initialBaseUrl);
    return {
      baseUrl: initialBaseUrl,
      raw: `GET ${initialUrl.pathname || '/'} HTTP/1.1\r\nHost: ${initialUrl.host}\r\nAccept: application/json\r\n\r\n`
    };
  }

  function exampleContent(format: ImportFormat): string {
    const origin = new URL(initialBaseUrl).origin;
    if (format === 'curl') {
      return `curl '${origin}/api/resource/17' \\\n  -H 'Accept: application/json'`;
    }
    if (format === 'openapi') return `openapi: 3.1.0
servers:
  - url: ${origin}
paths:
  /api/resource/{id}:
    get:
      responses:
        '200':
          description: Successful response`;
    return '';
  }

  const initial = initialRawForm();
  let mode = $state<ImportFormat>('raw');
  let baseUrl = $state(initial.baseUrl);
  let raw = $state(initial.raw);
  let content = $state('');
  let filename = $state('');
  let preview = $state<ImportPreview | null>(null);
  let result = $state<ImportResult | null>(null);
  let rawResult = $state<Exchange | null>(null);
  let busy = $state(false);
  let error = $state('');

  function selectMode(next: ImportFormat) {
    mode = next;
    preview = null;
    result = null;
    rawResult = null;
    error = '';
    filename = '';
    if (next !== 'raw') content = exampleContent(next);
  }

  async function selectedFile(event: Event) {
    const file = event.currentTarget instanceof HTMLInputElement ? event.currentTarget.files?.[0] : null;
    if (!file) return;
    filename = file.name;
    content = await file.text();
    preview = null;
  }

  async function parsePreview() {
    const documentMode = mode;
    if (documentMode === 'raw' || !content.trim()) return;
    await run(async () => {
      preview = await previewTrafficDocument(
        engagementId,
        documentMode,
        content,
        filename || null
      );
    });
  }

  async function importDocument() {
    const documentMode = mode;
    if (documentMode === 'raw') {
      await run(async () => {
        rawResult = await api<Exchange>(`engagements/${engagementId}/traffic/raw`, {
          method: 'POST',
          body: JSON.stringify({ base_url: baseUrl, raw })
        });
        await onimported(rawResult);
      });
      return;
    }
    if (!preview) return;
    await run(async () => {
      result = await importTrafficDocument(
        engagementId,
        documentMode,
        content,
        filename || null
      );
      await onimported(result);
    });
  }

  async function run(action: () => Promise<void>) {
    busy = true;
    error = '';
    try {
      await action();
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not process the import';
    } finally {
      busy = false;
    }
  }
</script>

<DialogShell eyebrow="REAL TRAFFIC INGESTION" title="Import Traffic" wide {onclose}>
  <div class="import-mode-tabs" role="tablist" aria-label="Import format">
    {#each importFormatOptions as option}
      <button class:active={mode === option.value} type="button" role="tab" aria-selected={mode === option.value} onclick={() => selectMode(option.value)}>{option.label}</button>
    {/each}
  </div>

  {#if result}
    <section class="import-result" aria-live="polite">
      <header><div><span class="eyebrow">{result.batch.display_id}</span><h3>{result.batch.import_format.toUpperCase()} Import</h3></div><strong class:partial={result.batch.status === 'partial'}>{result.batch.status}</strong></header>
      <div class="import-stats">
        <span><small>PROCESSED</small><strong>{result.batch.total_records}</strong></span><span><small>IMPORTED</small><strong>{result.batch.imported_count}</strong></span><span><small>RESPONSES</small><strong>{result.batch.response_count}</strong></span><span><small>SKIPPED</small><strong>{result.batch.skipped_count}</strong></span><span><small>NEW ENDPOINTS</small><strong>{result.batch.new_endpoint_count}</strong></span><span><small>KNOWN ENDPOINTS</small><strong>{result.batch.known_endpoint_count}</strong></span>
      </div>
      {#if result.batch.warnings.length}<details class="warning-list" open><summary>{importWarningLabel(result.batch.warnings)}</summary>{#each result.batch.warnings as warning}<p>{warning}</p>{/each}</details>{/if}
      <p class="form-note">Imported records are stored locally. No request was sent by this import.</p>
      <div class="dialog-actions"><button class="button primary" type="button" onclick={onclose}>Done</button></div>
    </section>
  {:else if rawResult}
    <section class="import-result" aria-live="polite"><header><div><span class="eyebrow">RAW HTTP</span><h3>Request imported</h3></div><strong>stored</strong></header><div class="import-stats"><span><small>METHOD</small><strong>{rawResult.method}</strong></span><span><small>SOURCE</small><strong>Raw HTTP</strong></span><span><small>STATUS</small><strong>{rawResult.response_status ?? 'Not observed'}</strong></span></div><p class="form-note">The request was parsed, scope-checked, and stored without sending traffic.</p><div class="dialog-actions"><button class="button primary" type="button" onclick={onclose}>Done</button></div></section>
  {:else if mode === 'raw'}
    <form class="stack-form" onsubmit={(event) => { event.preventDefault(); void importDocument(); }}>
      <label><span>Base URL</span><input bind:value={baseUrl} required type="url" spellcheck="false" /></label>
      <label><span>Raw request</span><textarea class="http-editor" bind:value={raw} required rows="14" spellcheck="false"></textarea></label>
      <p class="form-note">Parsed and checked against engagement scope before storage. Importing does not send the request.</p>
      {#if error}<p class="form-error" role="alert">{error}</p>{/if}
      <div class="dialog-actions"><button class="button ghost" type="button" onclick={onclose}>Cancel</button><button class="button primary" type="submit" disabled={busy || !raw.trim()}>{busy ? 'Importing…' : 'Import request'}</button></div>
    </form>
  {:else}
    <div class="stack-form">
      {#if preview}
        <section class="import-preview" aria-live="polite">
          <header><div><span class="eyebrow">REDACTED PREVIEW</span><h3>{mode.toUpperCase()} summary</h3></div><strong>{preview.accepted_count} accepted</strong></header>
          <div class="import-stats"><span><small>PROCESSED</small><strong>{preview.total_records}</strong></span><span><small>ACCEPTED</small><strong>{preview.accepted_count}</strong></span><span><small>RESPONSES</small><strong>{preview.response_count}</strong></span><span><small>SKIPPED</small><strong>{preview.skipped_count}</strong></span><span><small>WARNINGS</small><strong>{preview.warnings.length}</strong></span></div>
          {#if preview.requests.length}<div class="preview-records">{#each preview.requests as item}<article class:blocked={!item.scope_allowed}><code>{item.method}</code><strong>{item.url}</strong><span>{item.header_count} headers · {item.cookie_count} cookies · {item.body_bytes} body bytes</span><em>{item.scope_allowed ? 'IN SCOPE' : 'OUT OF SCOPE'}</em></article>{/each}</div>{/if}
          {#if preview.endpoints.length}<div class="preview-records">{#each preview.endpoints as item}<article><code>{item.method}</code><strong>{item.path_template}</strong><span>{item.server_url ?? 'No declared server'}{item.operation_id ? ` · ${item.operation_id}` : ''}</span><em>{item.auth.join(', ') || 'AUTH NOT DECLARED'}</em></article>{/each}</div>{/if}
          {#if preview.warnings.length}<details class="warning-list"><summary>{importWarningLabel(preview.warnings)}</summary>{#each preview.warnings as warning}<p>{warning}</p>{/each}</details>{/if}
        </section>
      {:else}
        {#if mode !== 'curl'}<label><span>{mode === 'har' ? 'HAR file' : 'OpenAPI JSON or YAML file'}</span><input type="file" accept={mode === 'har' ? '.har,application/json' : '.json,.yaml,.yml,application/json,application/yaml,text/yaml'} onchange={selectedFile} /></label>{/if}
        <label><span>{mode === 'curl' ? 'cURL command' : mode === 'har' ? 'HAR document' : 'OpenAPI document'}</span><textarea class="import-editor" bind:value={content} rows="12" spellcheck="false" placeholder={mode === 'har' ? 'Paste HAR 1.2 JSON or choose a file' : undefined}></textarea></label>
        <p class="form-note">{mode === 'curl' ? 'The command is parsed as inert text and is never passed to a shell.' : mode === 'openapi' ? 'Servers remain metadata. External references are not fetched and no endpoint is contacted.' : 'HAR is treated as untrusted data. Entries are bounded, scope-checked, and never executed.'}</p>
      {/if}
      {#if error}<p class="form-error" role="alert">{error}</p>{/if}
      <div class="dialog-actions">{#if preview}<button class="button ghost" type="button" onclick={() => (preview = null)}>Edit source</button><button class="button primary" type="button" onclick={importDocument} disabled={busy}>{busy ? 'Importing…' : `Import ${preview.accepted_count} records`}</button>{:else}<button class="button ghost" type="button" onclick={onclose}>Cancel</button><button class="button primary" type="button" onclick={parsePreview} disabled={busy || !content.trim()}>{busy ? 'Parsing…' : 'Parse and preview'}</button>{/if}</div>
    </div>
  {/if}
</DialogShell>
