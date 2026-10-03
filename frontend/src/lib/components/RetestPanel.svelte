<script lang="ts">
  import type { Finding, Retest } from '../types';
  let { retests, findings, onopen }: { retests: Retest[]; findings: Finding[]; onopen: (findingId: string) => void } = $props();
  function title(id: string) { return findings.find((item) => item.id === id)?.title ?? 'Finding'; }
</script>
<section class="workspace-page lifecycle-page" aria-labelledby="retest-title"><header class="workspace-header"><div><span class="eyebrow">VERIFICATION LOG</span><h1 id="retest-title">Retests</h1><p>Every verification attempt is preserved; the newest result appears on its finding.</p></div></header><div class="retest-ledger">{#each retests as item}<button type="button" onclick={() => onopen(item.finding_id)}><code>{item.display_id}</code><div><strong>{item.finding_display_id} · {title(item.finding_id)}</strong><small>{item.operator_notes || 'No operator notes'}</small></div><span class="retest-result">{item.status}</span><time>{new Date(item.tested_at).toLocaleString()}</time></button>{:else}<div class="empty-workspace"><span class="empty-glyph">↻</span><strong>No retests</strong><p>Open a finding to record its first verification attempt.</p></div>{/each}</div></section>
