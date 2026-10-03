<script lang="ts">
  import { api } from '../api';
  import type { Exchange } from '../types';
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
    onimported: (exchange: Exchange) => void;
  } = $props();

  function initialForm() {
    const initialUrl = new URL(initialBaseUrl);
    return {
      baseUrl: initialBaseUrl,
      raw: `GET ${initialUrl.pathname || '/'} HTTP/1.1\r\nHost: ${initialUrl.host}\r\nAccept: application/json\r\n\r\n`
    };
  }

  const initial = initialForm();
  let baseUrl = $state(initial.baseUrl);
  let raw = $state(initial.raw);
  let busy = $state(false);
  let error = $state('');

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = '';
    try {
      const exchange = await api<Exchange>(`engagements/${engagementId}/traffic/raw`, {
        method: 'POST',
        body: JSON.stringify({ base_url: baseUrl, raw })
      });
      onimported(exchange);
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not import the request';
    } finally {
      busy = false;
    }
  }
</script>

<DialogShell eyebrow="TRAFFIC IMPORT" title="Store a raw HTTP request" {onclose}>
  <form class="stack-form" onsubmit={submit}>
    <label>
      <span>Base URL</span>
      <input bind:value={baseUrl} required type="url" spellcheck="false" />
    </label>
    <label>
      <span>Raw request</span>
      <textarea class="http-editor" bind:value={raw} required rows="14" spellcheck="false"></textarea>
    </label>
    <p class="form-note">
      The request is parsed and checked against the engagement scope before it is stored. Importing
      does not send the request.
    </p>
    {#if error}<p class="form-error" role="alert">{error}</p>{/if}
    <div class="dialog-actions">
      <button class="button ghost" type="button" onclick={onclose}>Cancel</button>
      <button class="button primary" type="submit" disabled={busy || !raw.trim()}>
        {busy ? 'Importing…' : 'Import request'}
      </button>
    </div>
  </form>
</DialogShell>
