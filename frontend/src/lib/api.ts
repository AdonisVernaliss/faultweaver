export function apiPath(path: string): string {
  return `/api/${path.replace(/^\/+/, '')}`;
}
