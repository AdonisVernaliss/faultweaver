<script lang="ts">
  import type { Snippet } from 'svelte';

  let {
    eyebrow,
    title,
    onclose,
    children
  }: { eyebrow: string; title: string; onclose: () => void; children: Snippet } = $props();

  function onBackdrop(event: MouseEvent) {
    if (event.target === event.currentTarget) onclose();
  }
</script>

<svelte:window onkeydown={(event) => event.key === 'Escape' && onclose()} />

<div class="dialog-backdrop" role="presentation" onclick={onBackdrop}>
  <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
    <header class="dialog-header">
      <div>
        <span class="eyebrow">{eyebrow}</span>
        <h2 id="dialog-title">{title}</h2>
      </div>
      <button class="icon-button" type="button" aria-label="Close dialog" onclick={onclose}>×</button>
    </header>
    <div class="dialog-body">{@render children()}</div>
  </div>
</div>
