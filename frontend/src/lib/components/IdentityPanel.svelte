<script lang="ts">
  import { api } from '../api';
  import type { Identity } from '../types';

  let {
    engagementId,
    identities,
    onchanged
  }: {
    engagementId: string;
    identities: Identity[];
    onchanged: () => Promise<void>;
  } = $props();

  let editingId = $state<string | null>(null);
  let formOpen = $state(false);
  let name = $state('');
  let description = $state('');
  let bearerToken = $state('');
  let apiKeyHeader = $state('');
  let apiKeyValue = $state('');
  let cookies = $state('');
  let customHeaders = $state('');
  let busy = $state(false);
  let error = $state('');

  function openCreate() {
    editingId = null;
    name = '';
    description = '';
    bearerToken = '';
    apiKeyHeader = '';
    apiKeyValue = '';
    cookies = '';
    customHeaders = '';
    error = '';
    formOpen = true;
  }

  function openEdit(identity: Identity) {
    editingId = identity.id;
    name = identity.name;
    description = identity.description;
    bearerToken = '';
    apiKeyHeader = identity.api_key_header ?? '';
    apiKeyValue = '';
    cookies = '';
    customHeaders = '';
    error = '';
    formOpen = true;
  }

  function cookieEntries() {
    return cookies
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const separator = line.indexOf('=');
        if (separator < 1) throw new Error('Cookies must use name=value, one per line');
        return { name: line.slice(0, separator).trim(), value: line.slice(separator + 1).trim() };
      });
  }

  function headerEntries() {
    return customHeaders
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const separator = line.indexOf(':');
        if (separator < 1) throw new Error('Custom headers must use Name: value, one per line');
        return { name: line.slice(0, separator).trim(), value: line.slice(separator + 1).trim() };
      });
  }

  async function save(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = '';
    try {
      const payload: Record<string, unknown> = { name, description };
      if (!editingId || bearerToken) payload.bearer_token = bearerToken || null;
      if (!editingId || apiKeyValue) {
        payload.api_key_header = apiKeyHeader || null;
        payload.api_key_value = apiKeyValue || null;
      }
      if (!editingId || cookies) payload.cookies = cookieEntries();
      if (!editingId || customHeaders) payload.custom_headers = headerEntries();
      const path = editingId
        ? `engagements/${engagementId}/identities/${editingId}`
        : `engagements/${engagementId}/identities`;
      await api<Identity>(path, {
        method: editingId ? 'PATCH' : 'POST',
        body: JSON.stringify(payload)
      });
      formOpen = false;
      await onchanged();
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not save the identity';
    } finally {
      busy = false;
    }
  }

  async function remove(identity: Identity) {
    if (identity.is_anonymous) return;
    busy = true;
    error = '';
    try {
      await api<void>(`engagements/${engagementId}/identities/${identity.id}`, {
        method: 'DELETE'
      });
      await onchanged();
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not delete the identity';
    } finally {
      busy = false;
    }
  }
</script>

<section class="workspace-page" aria-labelledby="identity-title">
  <header class="workspace-header">
    <div>
      <span class="eyebrow">AUTHENTICATION CONTEXTS</span>
      <h1 id="identity-title">Identities</h1>
      <p>Keep replay credentials local, structured, and redacted in workspace views.</p>
    </div>
    <button class="button primary" type="button" onclick={openCreate}>＋ Add identity</button>
  </header>

  {#if error}<p class="form-error" role="alert">{error}</p>{/if}

  <div class="identity-grid">
    {#each identities as identity (identity.id)}
      <article class="identity-card">
        <header>
          <div>
            <span class:anonymous={identity.is_anonymous} class="identity-kind">
              {identity.is_anonymous ? 'ANONYMOUS' : 'AUTHENTICATED'}
            </span>
            <h2>{identity.name}</h2>
          </div>
          {#if !identity.is_anonymous}
            <div class="card-actions">
              <button class="text-action" type="button" onclick={() => openEdit(identity)}>Edit</button>
              <button class="text-action danger-text" type="button" disabled={busy} onclick={() => remove(identity)}>Delete</button>
            </div>
          {/if}
        </header>
        <p>{identity.description || 'No description.'}</p>
        <dl class="credential-summary">
          <div><dt>Bearer</dt><dd>{identity.bearer_token ?? '—'}</dd></div>
          <div><dt>API key</dt><dd>{identity.api_key_header ?? '—'}</dd></div>
          <div><dt>Cookies</dt><dd>{identity.cookies.length}</dd></div>
          <div><dt>Custom headers</dt><dd>{identity.custom_headers.length}</dd></div>
        </dl>
      </article>
    {/each}
  </div>

  {#if formOpen}
    <form class="identity-editor stack-form" onsubmit={save}>
      <div class="editor-heading">
        <div><span class="eyebrow">{editingId ? 'UPDATE CONTEXT' : 'NEW CONTEXT'}</span><h2>{editingId ? 'Edit identity' : 'Add identity'}</h2></div>
        <button class="icon-button" type="button" aria-label="Close editor" onclick={() => (formOpen = false)}>×</button>
      </div>
      <div class="field-grid two">
        <label><span>Name</span><input bind:value={name} required maxlength="160" /></label>
        <label><span>Description</span><input bind:value={description} maxlength="10000" /></label>
      </div>
      <label><span>Bearer token <small>{editingId ? 'Leave blank to retain current token' : ''}</small></span><input bind:value={bearerToken} type="password" autocomplete="off" /></label>
      <div class="field-grid two">
        <label><span>API key header</span><input bind:value={apiKeyHeader} placeholder="X-API-Key" /></label>
        <label><span>API key value <small>{editingId ? 'Blank retains current value' : ''}</small></span><input bind:value={apiKeyValue} type="password" autocomplete="off" /></label>
      </div>
      <div class="field-grid two">
        <label><span>Cookies <small>name=value, one per line</small></span><textarea bind:value={cookies} rows="4" spellcheck="false"></textarea></label>
        <label><span>Custom headers <small>Name: value, one per line</small></span><textarea bind:value={customHeaders} rows="4" spellcheck="false"></textarea></label>
      </div>
      <p class="form-note">Saved secret values are never returned by the API. Blank credential fields preserve existing values while editing.</p>
      <div class="dialog-actions">
        <button class="button ghost" type="button" onclick={() => (formOpen = false)}>Cancel</button>
        <button class="button primary" type="submit" disabled={busy || !name.trim()}>{busy ? 'Saving…' : 'Save identity'}</button>
      </div>
    </form>
  {/if}
</section>
