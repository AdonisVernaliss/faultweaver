type FilterableRequest = {
  method: string;
  host: string;
  path: string;
  query: string;
  response_status: number | null;
  source: string;
};

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
    replay: 'REPLAY',
    crawler: 'CRAWLER'
  }[source] ?? source.toUpperCase();
}

export function filterRequests<T extends FilterableRequest>(
  requests: T[],
  filter: string,
  source: string
): T[] {
  const needle = filter.trim().toLowerCase();
  return requests.filter(
    (request) =>
      (!source || request.source === source) &&
      (!needle ||
        request.method.toLowerCase().includes(needle) ||
        request.host.toLowerCase().includes(needle) ||
        requestTarget(request.path, request.query).toLowerCase().includes(needle) ||
        String(request.response_status ?? '').includes(needle))
  );
}
