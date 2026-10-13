// Wire types — mirrors the Pydantic schemas in backend/app/schemas/*.
// Keep both sides in sync (the backend is the source of truth).

export type AiTool = "chatgpt" | "gemini" | "claude" | "copilot" | "other";
export type RiskCategory =
  | "none"
  | "pii"
  | "source_code"
  | "financial"
  | "confidential"
  | "credentials"
  | "other";
export type PolicyAction = "log_only" | "warn" | "block";
export type UserRole = "admin" | "employee";

export interface CaptureEvent {
  client_event_id: string;
  occurred_at: string; // ISO8601
  ai_tool: AiTool;
  domain: string;
  page_path?: string | null;
  prompt_text?: string | null;
  response_text?: string | null;
  was_blocked?: boolean;
}

export interface ShadowVisitEvent {
  client_event_id: string;
  occurred_at: string;
  domain: string;
  page_title?: string | null;
  markers: Record<string, boolean>;
}

export interface CaptureResponse {
  accepted: number;
  rejected: { client_event_id: string; reason: string }[];
  interaction_ids: string[];
}

export interface ShadowVisitResponse {
  first_seen: string[];
  capture_enabled_for: string[];
  risk: string | null;
}

export interface PolicyCheckResponse {
  action: PolicyAction;
  message: string | null;
  category: RiskCategory;
  confidence: number;
  flagged: boolean;
  rule_id: string | null;
  rule_name: string | null;
}

export interface UserOut {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  department: string | null;
  job_title: string | null;
  is_enrolled: boolean;
  consent_accepted: boolean;
  consent_version: string | null;
  consent_at: string | null;
  device_id: string | null;
  extension_version: string | null;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: UserOut;
}

export interface AiDomainsResponse {
  domains: string[];
  consent_version: string;
  presidio_enabled: boolean;
  semantic_enabled: boolean;
}

export interface UsageTotals {
  interactions: number;
  flagged: number;
  blocked: number;
  alerts: number;
  shadow_domains: number;
  active_users: number;
}

export interface UsageResponse {
  days: number;
  totals: UsageTotals;
  by_day: { date: string; total: number; flagged: number; blocked: number }[];
  by_tool: { key: string; label: string | null; count: number }[];
  by_category: { key: string; label: string | null; count: number }[];
  top_users: { key: string; label: string | null; count: number }[];
}

/** runtime.sendMessage status reply */
export interface StatusResponse {
  authed: boolean;
  consented: boolean;
  enrolled: boolean;
  user: UserOut | null;
  queued: number;
  apiBase: string;
  consentVersion: string | null;
}

export interface QueuedBatch {
  events: CaptureEvent[];
}
