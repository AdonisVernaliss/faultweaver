export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export function apiPath(path: string): string {
  return `/api/${path.replace(/^\/+/, '')}`;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiPath(path), {
    ...init,
    headers: {
      ...(init?.body ? { 'content-type': 'application/json' } : {}),
      ...init?.headers
    }
  });

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const error = (await response.json()) as { detail?: string };
      if (error.detail) message = error.detail;
    } catch {
      // Preserve the HTTP status text when the API did not return JSON.
    }
    throw new ApiError(message, response.status);
  }

  return (await response.json()) as T;
}
