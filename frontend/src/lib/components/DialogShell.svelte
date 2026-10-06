<script lang="ts">
  import { onMount, type Snippet } from 'svelte';

  let {
    eyebrow,
    title,
    wide = false,
    onclose,
    children
  }: { eyebrow: string; title: string; wide?: boolean; onclose: () => void; children: Snippet } = $props();

  let dialog: HTMLDivElement;
  const focusable = () => [...dialog.querySelectorAll<HTMLElement>('button, input, select, textarea, a[href], [tabindex]')]
    .filter(element => !element.matches(':disabled, [tabindex="-1"]') && element.getClientRects().length);
  onMount(() => {
    const previous = document.activeElement as HTMLElement | null;
    (focusable()[0] ?? dialog).focus();
    return () => { if (previous?.isConnected) previous.focus(); };
  });

  function onKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') { event.preventDefault(); onclose(); }
    if (event.key !== 'Tab') return;
    const elements = focusable();
    const first = elements[0] ?? dialog;
    const last = elements.at(-1) ?? dialog;
    if (!dialog.contains(document.activeElement) || (event.shiftKey && document.activeElement === first)) {
      event.preventDefault(); (event.shiftKey ? last : first).focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault(); first.focus();
    }
  }

  function onBackdrop(event: MouseEvent) {
    if (event.target === event.currentTarget) onclose();
  }
</script>

<svelte:window onkeydown={onKeydown} />

<div class="dialog-backdrop" role="presentation" onclick={onBackdrop}>
  <div bind:this={dialog} tabindex="-1" class:wide class="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
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
