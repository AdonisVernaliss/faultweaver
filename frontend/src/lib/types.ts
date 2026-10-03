export type EngagementStatus = 'draft' | 'active' | 'reporting' | 'complete' | 'archived';

export interface Engagement {
  id: string;
  name: string;
  description: string;
  status: EngagementStatus;
  created_at: string;
  updated_at: string;
}

export interface EngagementDetail extends Engagement {
  scope_count: number;
  request_count: number;
}

export interface ScopeRule {
  id: string;
  engagement_id: string;
  scheme: string;
  hostname: string;
  port: number;
  path_prefix: string;
  active: boolean;
}

export interface HeaderEntry {
  name: string;
  value: string;
}

export interface Exchange {
  id: string;
  engagement_id: string;
  parent_exchange_id: string | null;
  source: 'raw_import' | 'replay';
  method: string;
  url: string;
  host: string;
  path: string;
  query: string;
  request_headers: HeaderEntry[];
  request_body: string | null;
  response_status: number | null;
  response_headers: HeaderEntry[];
  response_body: string | null;
  response_elapsed_ms: number | null;
  response_truncated: boolean;
  redirect_chain: string[];
  created_at: string;
}

export interface ExchangeDetail extends Exchange {
  raw_request: string;
}

export interface ExchangeList {
  items: Exchange[];
  total: number;
}
