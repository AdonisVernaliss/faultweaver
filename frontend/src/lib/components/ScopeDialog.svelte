<script lang="ts">
  import { api } from '../api';
  import type { ScopeRule } from '../types';
  import DialogShell from './DialogShell.svelte';

  let {
    engagementId,
    onclose,
    oncreated
  }: {
    engagementId: string;
    onclose: () => void;
    oncreated: (scope: ScopeRule) => void;
  } = $props();

  let scheme = $state('http');
  let hostname = $state('localhost');
  let port = $state(3000);
  let pathPrefix = $state('/');
  let busy = $state(false);
  let error = $state('');

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = '';
    try {
      const scope = await api<ScopeRule>(`engagements/${engagementId}/scopes`, {
        method: 'POST',
        body: JSON.stringify({ scheme, hostname, port, path_prefix: pathPrefix })
      });
      oncreated(scope);
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not save the scope rule';
    } finally {
      busy = false;
    }
  }
</script>

<DialogShell eyebrow="NETWORK BOUNDARY" title="Authorize target scope" {onclose}>
  <form class="stack-form" onsubmit={submit}>
    <div class="field-grid three">
      <label>
        <span>Scheme</span>
        <select bind:value={scheme}>
          <option value="http">http</option>
          <option value="https">https</option>
        </select>
      </label>
      <label class="wide-field">
        <span>Hostname</span>
        <input bind:value={hostname} required placeholder="localhost" />
      </label>
      <label>
        <span>Port</span>
        <input bind:value={port} required type="number" min="1" max="65535" />
      </label>
    </div>
    <label>
      <span>Allowed path prefix</span>
      <input bind:value={pathPrefix} required placeholder="/" />
    </label>
    <div class="boundary-preview">
      <span>AUTHORIZED ORIGIN</span>
      <code>{scheme}://{hostname || 'host'}:{port}{pathPrefix || '/'}</code>
    </div>
    <p class="form-note">
      Scheme, hostname, port, and path are enforced by the backend before every outbound request
      and redirect.
    </p>
    {#if error}<p class="form-error" role="alert">{error}</p>{/if}
    <div class="dialog-actions">
      <button class="button ghost" type="button" onclick={onclose}>Cancel</button>
      <button class="button primary" type="submit" disabled={busy || !hostname.trim()}>
        {busy ? 'Saving…' : 'Add authorized scope'}
      </button>
    </div>
  </form>
</DialogShell>
