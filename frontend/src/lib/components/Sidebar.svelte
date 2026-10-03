<script lang="ts">
  import type { EngagementDetail } from '../types';

  let {
    engagement,
    requestCount,
    attackSurfaceCount,
    identityCount,
    candidateCount,
    findingCount,
    evidenceCount,
    retestCount,
    attackChainCount,
    activeView,
    onview,
    oncreate
  }: {
    engagement: EngagementDetail | null;
    requestCount: number;
    attackSurfaceCount: number;
    identityCount: number;
    candidateCount: number;
    findingCount: number;
    evidenceCount: number;
    retestCount: number;
    attackChainCount: number;
    activeView: 'requests' | 'attack-surface' | 'identities' | 'matrix' | 'candidates' | 'findings' | 'evidence' | 'retests' | 'attack-chains';
    onview: (view: 'requests' | 'attack-surface' | 'identities' | 'matrix' | 'candidates' | 'findings' | 'evidence' | 'retests' | 'attack-chains') => void;
    oncreate: () => void;
  } = $props();

  const futureSections = ['Report'];
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
    <button aria-label="Requests" class:active={activeView === 'requests'} class="nav-item" type="button" onclick={() => onview('requests')} aria-current={activeView === 'requests' ? 'page' : undefined}>
      <span class="nav-glyph">↗</span><span>Requests</span><em>{requestCount}</em>
    </button>
    <button aria-label="Attack Surface" class:active={activeView === 'attack-surface'} class="nav-item" type="button" onclick={() => onview('attack-surface')} aria-current={activeView === 'attack-surface' ? 'page' : undefined}>
      <span class="nav-glyph">⌗</span><span>Attack Surface</span><em>{attackSurfaceCount}</em>
    </button>
    <button aria-label="Identities" class:active={activeView === 'identities'} class="nav-item" type="button" onclick={() => onview('identities')}><span class="nav-glyph">◎</span><span>Identities</span><em>{identityCount}</em></button>
    <button aria-label="Auth matrix" class:active={activeView === 'matrix'} class="nav-item" type="button" onclick={() => onview('matrix')}><span class="nav-glyph">▦</span><span>Auth matrix</span></button>
    <button aria-label="Candidates" class:active={activeView === 'candidates'} class="nav-item" type="button" onclick={() => onview('candidates')}><span class="nav-glyph">◇</span><span>Candidates</span><em>{candidateCount}</em></button>
    <button aria-label="Findings" class:active={activeView === 'findings'} class="nav-item" type="button" onclick={() => onview('findings')}><span class="nav-glyph">◆</span><span>Findings</span><em>{findingCount}</em></button>
    <button aria-label="Evidence" class:active={activeView === 'evidence'} class="nav-item" type="button" onclick={() => onview('evidence')}><span class="nav-glyph">▣</span><span>Evidence</span><em>{evidenceCount}</em></button>
    <button aria-label="Retests" class:active={activeView === 'retests'} class="nav-item" type="button" onclick={() => onview('retests')}><span class="nav-glyph">↻</span><span>Retests</span><em>{retestCount}</em></button>
    <button aria-label="Attack Chains" class:active={activeView === 'attack-chains'} class="nav-item" type="button" onclick={() => onview('attack-chains')}><span class="nav-glyph">⌁</span><span>Attack Chains</span><em>{attackChainCount}</em></button>
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
