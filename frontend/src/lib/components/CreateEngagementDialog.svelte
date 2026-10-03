<script lang="ts">
  import { api } from '../api';
  import type { Engagement } from '../types';
  import DialogShell from './DialogShell.svelte';

  let {
    onclose,
    oncreated
  }: { onclose: () => void; oncreated: (engagement: Engagement) => void } = $props();

  let name = $state('');
  let description = $state('');
  let busy = $state(false);
  let error = $state('');

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = '';
    try {
      const engagement = await api<Engagement>('engagements', {
        method: 'POST',
        body: JSON.stringify({ name, description })
      });
      oncreated(engagement);
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Could not create the engagement';
    } finally {
      busy = false;
    }
  }
</script>

<DialogShell eyebrow="ENGAGEMENT" title="Start an authorized assessment" {onclose}>
  <form class="stack-form" onsubmit={submit}>
    <label>
      <span>Name</span>
      <input bind:value={name} required maxlength="160" placeholder="Q4 tenant isolation review" />
    </label>
    <label>
      <span>Description <small>optional</small></span>
      <textarea
        bind:value={description}
        rows="4"
        maxlength="10000"
        placeholder="Purpose, authorization reference, and assessment context"
      ></textarea>
    </label>
    <p class="form-note">
      Creating an engagement does not send traffic. Add an explicit scope before importing or
      replaying requests.
    </p>
    {#if error}<p class="form-error" role="alert">{error}</p>{/if}
    <div class="dialog-actions">
      <button class="button ghost" type="button" onclick={onclose}>Cancel</button>
      <button class="button primary" type="submit" disabled={busy || !name.trim()}>
        {busy ? 'Creating…' : 'Create engagement'}
      </button>
    </div>
  </form>
</DialogShell>
