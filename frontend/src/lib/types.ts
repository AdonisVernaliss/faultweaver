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
  identity_id: string | null;
  auth_source: 'original' | 'identity';
  operator_modified: boolean;
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

export interface Identity {
  id: string;
  engagement_id: string;
  name: string;
  description: string;
  is_anonymous: boolean;
  bearer_token: string | null;
  api_key_header: string | null;
  api_key_value: string | null;
  cookies: HeaderEntry[];
  custom_headers: HeaderEntry[];
  created_at: string;
  updated_at: string;
}

export interface JsonFieldChange {
  path: string;
  a: unknown;
  b: unknown;
}

export interface ResponseDiff {
  status: { a: number | null; b: number | null; changed: boolean };
  content_type: { a: string | null; b: string | null; changed: boolean };
  body_size: { a: number; b: number; delta: number };
  normalized_similarity: number;
  json: {
    present_a: boolean;
    present_b: boolean;
    added_fields: string[];
    removed_fields: string[];
    changed_fields: JsonFieldChange[];
    structural_similarity: number;
  };
  redirects: { a: string[]; b: string[]; changed: boolean };
  header_differences: { name: string; a: string | null; b: string | null }[];
}

export interface Candidate {
  id: string;
  engagement_id: string;
  comparison_id: string;
  original_exchange_id: string;
  supporting_replay_ids: string[];
  title: string;
  category: string;
  confidence: string;
  status: 'candidate' | 'reviewed' | 'promoted' | 'confirmed' | 'rejected';
  review_decision: 'Confirmed' | 'False Positive' | 'Informational' | 'Accepted' | null;
  reviewed_at: string | null;
  archived_at: string | null;
  finding_id: string | null;
  reasoning: string[];
  notes: string;
  target: { method: string; host: string; path: string };
  original: Exchange | null;
  supporting_replays: Exchange[];
  comparison_result: Record<string, unknown>;
  identities: { id: string; name: string }[];
  response_statuses: { exchange_id: string; identity_id: string | null; status: number | null }[];
  operator_notes: OperatorNote[];
  created_at: string;
  updated_at: string;
}

export interface OperatorNote {
  id: string;
  author_label: string;
  body: string;
  created_at: string;
}

export type Severity = 'Critical' | 'High' | 'Medium' | 'Low' | 'Informational';
export type FindingStatus =
  | 'Open'
  | 'In Remediation'
  | 'Ready for Retest'
  | 'Fixed'
  | 'Accepted Risk'
  | 'Closed';
export type RetestStatus = 'Still Vulnerable' | 'Partially Fixed' | 'Fixed' | 'Unable to Retest';

export interface FindingHistory {
  id: string;
  event_type: string;
  summary: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface Retest {
  id: string;
  engagement_id: string;
  finding_id: string;
  finding_display_id: string;
  display_id: string;
  status: RetestStatus;
  tested_at: string;
  operator_notes: string;
  evidence_ids: string[];
  created_at: string;
  updated_at: string;
  notes: OperatorNote[];
}

export interface Finding {
  id: string;
  engagement_id: string;
  display_id: string;
  candidate_id: string | null;
  title: string;
  category: string;
  severity: Severity;
  status: FindingStatus;
  affected_asset: string;
  affected_endpoints: string[];
  description: string;
  impact: string;
  reproduction_steps: string[];
  remediation: string;
  references: string[];
  supporting_original_exchange_id: string | null;
  supporting_comparison_id: string | null;
  confirmed_at: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  latest_retest: { display_id: string; status: RetestStatus; tested_at: string } | null;
  evidence_ids: string[];
  notes: OperatorNote[];
  retests: Retest[];
  history: FindingHistory[];
}

export type EvidenceType =
  | 'HTTP Request/Response'
  | 'Replay'
  | 'Response Comparison'
  | 'Operator Note'
  | 'Text Excerpt';

export interface Evidence {
  id: string;
  engagement_id: string;
  display_id: string;
  evidence_type: EvidenceType;
  title: string;
  snapshot: Record<string, unknown>;
  source_exchange_id: string | null;
  source_comparison_id: string | null;
  source_candidate_id: string | null;
  finding_id: string | null;
  author_label: string;
  captured_at: string;
  notes: OperatorNote[];
}

export interface Comparison {
  id: string;
  engagement_id: string;
  original_exchange_id: string;
  replay_a: Exchange;
  replay_b: Exchange;
  identity_a_id: string;
  identity_b_id: string;
  result: {
    normalized_a: Record<string, unknown>;
    normalized_b: Record<string, unknown>;
    diff: ResponseDiff;
  };
  candidate: Candidate | null;
  created_at: string;
}

export interface AuthorizationMatrixCell {
  state: 'observed' | 'missing_response' | 'not_tested';
  status: number | null;
  evidence_request_id: string | null;
}

export interface AuthorizationMatrix {
  identities: { id: string; name: string; is_anonymous: boolean }[];
  rows: {
    method: string;
    host: string;
    path: string;
    original_request_id: string;
    cells: Record<string, AuthorizationMatrixCell>;
  }[];
}
