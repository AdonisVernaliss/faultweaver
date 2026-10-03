<script lang="ts">
  import type { EngagementDetail } from '../types';

  let {
    engagement,
    requestCount,
    oncreate
  }: { engagement: EngagementDetail | null; requestCount: number; oncreate: () => void } = $props();

  const futureSections = ['Identities', 'Candidates', 'Findings', 'Evidence', 'Attack Chains', 'Report'];
</script>

<aside class="sidebar">
  <div class="brand-block">
    <div class="brand-mark" aria-hidden="true"><span></span><span></span><span></span></div>
    <div><strong>Faultweaver</strong><small>LOCAL WORKSPACE</small></div>
  </div>

  <div class="sidebar-section">
    <span class="section-label">ENGAGEMENT</span>
    {#if engagement}
      <div class="engagement-summary">
        <span class="engagement-initial">{engagement.name.slice(0, 2).toUpperCase()}</span>
        <div><strong>{engagement.name}</strong><small>{engagement.status}</small></div>
      </div>
    {:else}
      <p class="muted-copy">No engagement selected.</p>
    {/if}
    <button class="text-action" type="button" onclick={oncreate}>＋ New engagement</button>
  </div>

  <nav aria-label="Engagement workspace">
    <a class="nav-item active" href="#request-explorer" aria-current="page">
      <span class="nav-glyph">↗</span><span>Requests</span><em>{requestCount}</em>
    </a>
    <a class="nav-item" href="#scope">
      <span class="nav-glyph">⌾</span><span>Scope</span>
    </a>
    {#each futureSections as section}
      <span class="nav-item disabled" aria-disabled="true">
        <span class="nav-glyph">·</span><span>{section}</span><small>LATER</small>
      </span>
    {/each}
  </nav>

  <div class="sidebar-footer">
    <span class="connection-dot"></span>
    <div><strong>Local engine</strong><small>NO CLOUD CONNECTION</small></div>
  </div>
</aside>
