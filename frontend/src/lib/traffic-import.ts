import { api } from './api';
import type { ImportFormat, ImportPreview, ImportResult } from './types';

export const importFormatOptions = [
  { value: 'raw', label: 'Raw HTTP' },
  { value: 'har', label: 'HAR' },
  { value: 'curl', label: 'cURL' },
  { value: 'openapi', label: 'OpenAPI' }
] as const satisfies ReadonlyArray<{ value: ImportFormat; label: string }>;

type DocumentFormat = Exclude<ImportFormat, 'raw'>;

export function previewTrafficDocument(
  engagementId: string,
  format: DocumentFormat,
  content: string,
  filename: string | null
): Promise<ImportPreview> {
  return api<ImportPreview>(`engagements/${engagementId}/imports/${format}/preview`, {
    method: 'POST',
    body: JSON.stringify({ content, filename })
  });
}

export function importTrafficDocument(
  engagementId: string,
  format: DocumentFormat,
  content: string,
  filename: string | null
): Promise<ImportResult> {
  return api<ImportResult>(`engagements/${engagementId}/imports/${format}`, {
    method: 'POST',
    body: JSON.stringify({ content, filename })
  });
}
