export function requestTarget(path: string, query: string): string {
  return query ? `${path}?${query}` : path;
}

export function formatDuration(milliseconds: number | null): string {
  if (milliseconds === null) return '—';
  if (milliseconds < 1) return '<1 ms';
  return `${Math.round(milliseconds)} ms`;
}

export function sourceLabel(source: string): string {
  return {
    raw_import: 'RAW HTTP',
    har: 'HAR',
    curl: 'cURL',
    openapi: 'OPENAPI',
    manual: 'MANUAL',
    replay: 'REPLAY'
  }[source] ?? source.toUpperCase();
}
