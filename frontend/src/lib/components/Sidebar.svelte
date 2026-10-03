<script lang="ts">
  import type { EngagementDetail } from '../types';

  let {
    engagement,
    requestCount,
    identityCount,
    candidateCount,
    activeView,
    onview,
    oncreate
  }: {
    engagement: EngagementDetail | null;
    requestCount: number;
    identityCount: number;
    candidateCount: number;
    activeView: 'requests' | 'identities' | 'matrix' | 'candidates';
    onview: (view: 'requests' | 'identities' | 'matrix' | 'candidates') => void;
    oncreate: () => void;
  } = $props();

  const futureSections = ['Findings', 'Evidence', 'Attack Chains', 'Report'];
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
    <button class:active={activeView === 'requests'} class="nav-item" type="button" onclick={() => onview('requests')} aria-current={activeView === 'requests' ? 'page' : undefined}>
      <span class="nav-glyph">↗</span><span>Requests</span><em>{requestCount}</em>
    </button>
    <button class:active={activeView === 'identities'} class="nav-item" type="button" onclick={() => onview('identities')}><span class="nav-glyph">◎</span><span>Identities</span><em>{identityCount}</em></button>
    <button class:active={activeView === 'matrix'} class="nav-item" type="button" onclick={() => onview('matrix')}><span class="nav-glyph">▦</span><span>Auth matrix</span></button>
    <button class:active={activeView === 'candidates'} class="nav-item" type="button" onclick={() => onview('candidates')}><span class="nav-glyph">◇</span><span>Candidates</span><em>{candidateCount}</em></button>
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
