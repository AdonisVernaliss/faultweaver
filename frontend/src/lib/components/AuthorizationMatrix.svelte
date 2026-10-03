<script lang="ts">
  import type { AuthorizationMatrix as Matrix } from '../types';

  let { matrix, onopen }: { matrix: Matrix; onopen: (id: string) => void } = $props();
</script>

<section class="workspace-page" aria-labelledby="matrix-title">
  <header class="workspace-header"><div><span class="eyebrow">OBSERVED EVIDENCE</span><h1 id="matrix-title">Authorization matrix</h1><p>Response statuses by route and identity. Empty cells are explicitly not tested.</p></div></header>
  <div class="matrix-scroll">
    <table class="auth-matrix">
      <thead><tr><th>REQUEST</th>{#each matrix.identities as identity}<th>{identity.name}</th>{/each}</tr></thead>
      <tbody>
        {#each matrix.rows as row}
          <tr><th><span class="method-badge">{row.method}</span><div><code>{row.path}</code><small>{row.host}</small></div></th>{#each matrix.identities as identity}{@const cell = row.cells[identity.id]}<td class:observed={cell.state === 'observed'} class:missing={cell.state === 'missing_response'}>{#if cell.evidence_request_id}<button type="button" onclick={() => onopen(cell.evidence_request_id!)}><strong>{cell.status ?? '—'}</strong><small>{cell.state.replace('_', ' ')}</small></button>{:else}<span><strong>—</strong><small>not tested</small></span>{/if}</td>{/each}</tr>
        {:else}<tr><td colspan={matrix.identities.length + 1} class="matrix-empty">Import requests to establish matrix rows.</td></tr>{/each}
      </tbody>
    </table>
  </div>
</section>
