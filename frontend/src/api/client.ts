// Typed API client. Token lives in localStorage for this demo build
// (documented tradeoff vs HttpOnly cookies — see README "Known limitations").

export type UserRole = "admin" | "employee";
export type RiskCategory =
  | "none" | "pii" | "source_code" | "financial" | "confidential" | "credentials" | "other";
export type PolicyAction = "log_only" | "warn" | "block";
export type AiTool = "chatgpt" | "gemini" | "claude" | "copilot" | "other";

export interface User {
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

export interface Interaction {
  id: string;
  user_id: string;
  user_email: string | null;
  device_id: string | null;
  ai_tool: AiTool;
  domain: string;
  page_path: string | null;
  is_known_platform: boolean;
  is_first_seen: boolean;
  shadow_risk: "low" | "medium" | "high" | "unknown" | null;
  prompt_text: string | null;
  response_text: string | null;
  prompt_hash: string | null;
  redacted_preview: string | null;
  classification_status: "pending" | "complete" | "failed" | "skipped";
  risk_category: RiskCategory;
  risk_score: number;
  classifier_version: string | null;
  is_flagged: boolean;
  policy_rule_id: string | null;
  applied_action: PolicyAction | null;
  was_blocked: boolean;
  content_stored: boolean;
  purge_after: string | null;
  occurred_at: string;
  received_at: string;
}

export interface Finding {
  id: string;
  engine: string;
  label: string;
  score: number;
  start: number | null;
  end: number | null;
}

export interface InteractionDetail extends Interaction {
  findings: Finding[];
}

export interface PolicyRule {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  priority: number;
  category: RiskCategory | null;
  ai_tool: AiTool | null;
  domain: string | null;
  min_confidence: number;
  role_scope: UserRole | null;
  department_scope: string | null;
  action: PolicyAction;
  warn_message: string | null;
  block_message: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface UsageOut {
  days: number;
  totals: {
    interactions: number;
    flagged: number;
    blocked: number;
    shadow_domains: number;
    active_users: number;
  };
  by_day: { date: string; total: number; flagged: number; blocked: number }[];
  by_tool: { key: string; label: string | null; count: number }[];
  by_category: { key: string; label: string | null; count: number }[];
  top_users: { key: string; label: string | null; count: number }[];
}

export interface ShadowDomain {
  domain: string;
  first_seen: string;
  last_seen: string;
  interactions: number;
  users: number;
  risk: "low" | "medium" | "high" | "unknown" | null;
  is_known_platform: boolean;
}

export interface DaySummary {
  date: string;
  browser_active_seconds: number; // focused tab + OS input recent
  browser_idle_seconds: number;   // focused tab + no input
  other_seconds: number;          // another app focused + input recent
  away_seconds: number;           // no input at all
  audible_seconds: number;        // media playing in the focused tab
}

export interface TeamDayRow extends DaySummary {
  user_id: string;
  user_email: string;
  user_name: string;
}

export interface TopDomainRow {
  domain: string;
  seconds: number;
}

/** One comparison window of browser time, summed over the scope. */
export interface PeriodTotals {
  browser_active_seconds: number;
  browser_idle_seconds: number;
  other_seconds: number;
  away_seconds: number;
  audible_seconds: number;
  segments: number;
}

/** Percent change current vs previous; null = no baseline (shown as "new"). */
export interface TrendDeltas {
  browser_active_seconds: number | null;
  browser_idle_seconds: number | null;
  other_seconds: number | null;
  away_seconds: number | null;
}

/** Depth-of-work metrics — browser behaviour only, never a verdict. */
export interface FocusMetrics {
  focus_blocks: number;
  context_switches: number;
  switches_per_day: number;
  longest_focus_seconds: number;
  avg_focus_block_seconds: number;
}

export interface UserTrendRow {
  user_id: string;
  user_email: string;
  user_name: string;
  current: PeriodTotals;
  previous: PeriodTotals;
  delta_pct: number | null;
}

export interface TrendsOut {
  window_days: number;
  scope: "team" | "user";
  user_id: string | null;
  current: PeriodTotals;
  previous: PeriodTotals;
  deltas: TrendDeltas;
  focus: FocusMetrics;
  daily: DaySummary[]; // current window only, ascending
  users: UserTrendRow[];
}

/** The three weighted parts of a day's focus score, each 0–100. */
export interface FocusComponents {
  share_pct: number;      // focused tab vs all keyboard-tracked time
  continuity_pct: number; // avg focus block vs the 25-minute target
  calm_pct: number;       // context switches vs the 12/day baseline
}

/** One day's honest focus number — browser focus, never work quality. */
export interface FocusDayRow {
  date: string;
  focus_score: number | null; // 0–100, null = no focused-tab time (shown as "—")
  components: FocusComponents | null;
  focus_seconds: number;
  browser_active_seconds: number;
  browser_idle_seconds: number;
  other_seconds: number;
  away_seconds: number; // reported, but counts against no component
  focus_blocks: number;
  context_switches: number;
  longest_focus_seconds: number;
}

export interface FocusOut {
  window_days: number;
  user_id: string;
  user_email: string;
  user_name: string;
  average_score: number | null; // mean over days WITH focused-tab time
  days: FocusDayRow[]; // ascending by date
}

/** The week's focus rollup for one person — the daily score, rolled up. */
export interface DigestFocus {
  average_score: number | null; // mean over days WITH focused-tab time
  days_scored: number;
  best_day: string | null;
  best_day_score: number | null;
  focus_seconds: number;
  focus_blocks: number;
  context_switches: number;
  longest_focus_seconds: number;
}

/** The same person's week of AI interactions — counts + tool mix, never text. */
export interface DigestAiUsage {
  interactions: number;
  flagged: number;
  blocked: number;
  by_tool: { key: string; label: string | null; count: number }[];
}

/** One person's week on a page (ISO week, per-person by design). */
export interface DigestOut {
  week: string; // e.g. "2026-W43"
  week_start: string; // Monday
  week_end: string; // Sunday
  user_id: string;
  user_email: string;
  user_name: string;
  totals: PeriodTotals;
  tracked_days: number;
  focus: DigestFocus;
  top_domains: TopDomainRow[];
  ai_usage: DigestAiUsage;
  days: FocusDayRow[]; // the week's days, ascending
}

export interface TimeSegment {
  id: string;
  kind: "tab" | "away";
  domain: string | null;
  page_path: string | null;
  active_seconds: number;
  idle_seconds: number;
  audible_seconds: number;
  started_at: string;
  ended_at: string;
}

const TOKEN_KEY = "aidlp_token";
// Tab-scoped session override, used by the extension's "Open dashboard"
// handoff. sessionStorage is per-tab, so a user opening the dashboard from
// the extension never overwrites an admin's login in another tab (both tabs
// share localStorage but each keeps its own token).
const TAB_TOKEN_KEY = "aidlp_token_tab";

export const getToken = (): string | null =>
  sessionStorage.getItem(TAB_TOKEN_KEY) ?? localStorage.getItem(TOKEN_KEY);

/** Explicit sign-in: shared across tabs, and supersedes any handoff token. */
export const setToken = (token: string): void => {
  localStorage.setItem(TOKEN_KEY, token);
  sessionStorage.removeItem(TAB_TOKEN_KEY);
};

/** Extension handoff: bound to THIS tab only. */
export const setTabToken = (token: string): void => {
  sessionStorage.setItem(TAB_TOKEN_KEY, token);
};

export const clearToken = (): void => {
  localStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(TAB_TOKEN_KEY);
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...(init.headers as Record<string, string> | undefined),
  };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let resp: Response;
  try {
    resp = await fetch(`/api/v1${path}`, { ...init, headers });
  } catch (err) {
    throw new ApiError(0, `Backend unreachable (${(err as Error).message})`);
  }
  if (resp.status === 401) {
    clearToken();
    if (!path.startsWith("/auth/token")) window.dispatchEvent(new Event("aidlp:unauthorized"));
  }
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON */
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

/** Authenticated file download (can't use plain <a href>: needs the JWT). */
export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const resp = await fetch(`/api/v1${path}`, { headers });
  if (!resp.ok) throw new ApiError(resp.status, `Download failed (${resp.status})`);
  const blob = await resp.blob();
  const disposition = resp.headers.get("Content-Disposition") || "";
  const match = /filename="([^"]+)"/.exec(disposition);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = match?.[1] || fallbackName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

const qs = (params: Record<string, string | number | boolean | undefined | null>): string => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const out = search.toString();
  return out ? `?${out}` : "";
};

export interface RegisterPayload {
  email: string;
  full_name: string;
  password: string;
  department?: string;
  job_title?: string;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string; token_type: string; user: User }>("/auth/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username, password }).toString(),
    }),

  register: (payload: RegisterPayload) =>
    request<{ access_token: string; token_type: string; user: User }>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  me: () => request<User>("/auth/me"),

  consent: (deviceId: string | null, extensionVersion: string) =>
    request<User>("/auth/consent", {
      method: "POST",
      body: JSON.stringify({ device_id: deviceId, extension_version: extensionVersion, accepted: true }),
    }),

  interactions: (params: Record<string, string | number | boolean | undefined | null>) =>
    request<Page<Interaction>>(`/interactions${qs(params)}`),

  interaction: (id: string) => request<InteractionDetail>(`/interactions/${id}`),

  rules: (active?: boolean) => request<Page<PolicyRule>>(`/policy/rules${qs({ active })}`),

  createRule: (payload: Partial<PolicyRule>) =>
    request<PolicyRule>("/policy/rules", { method: "POST", body: JSON.stringify(payload) }),

  updateRule: (id: string, payload: Partial<PolicyRule>) =>
    request<PolicyRule>(`/policy/rules/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),

  deactivateRule: (id: string) =>
    request<{ detail: string }>(`/policy/rules/${id}`, { method: "DELETE" }),

  usage: (days: number, userId?: string) =>
    request<UsageOut>(`/analytics/usage${qs({ days, user_id: userId })}`),

  shadowAi: () => request<ShadowDomain[]>("/analytics/shadow-ai"),

  users: (page = 1, pageSize = 50) =>
    request<Page<User>>(`/users${qs({ page, page_size: pageSize })}`),

  createUser: (payload: {
    email: string;
    full_name: string;
    password: string;
    role: UserRole;
    department?: string;
    job_title?: string;
  }) => request<User>("/users", { method: "POST", body: JSON.stringify(payload) }),

  setUserStatus: (id: string, isActive: boolean) =>
    request<User>(`/users/${id}/status?is_active=${isActive}`, { method: "POST" }),

  activityMe: (days: number) =>
    request<{ window_days: number; user_id: string; user_email: string; user_name: string; days: DaySummary[] }>(
      `/activity/me${qs({ days })}`,
    ),

  activityTeamDaily: (days: number) => request<TeamDayRow[]>(`/activity/team-daily${qs({ days })}`),

  activityDaily: (days: number, userId?: string) =>
    request<DaySummary[]>(`/activity/daily${qs({ days, user_id: userId })}`),

  activityTopDomains: (days: number, userId?: string) =>
    request<TopDomainRow[]>(`/activity/top-domains${qs({ days, user_id: userId })}`),

  activitySegments: (days: number, userId?: string, limit = 100) =>
    request<TimeSegment[]>(`/activity/segments${qs({ days, user_id: userId, limit })}`),

  activityTrends: (days: number, userId?: string) =>
    request<TrendsOut>(`/activity/trends${qs({ days, user_id: userId })}`),

  activityFocus: (days: number, userId?: string) =>
    request<FocusOut>(`/activity/focus${qs({ days, user_id: userId })}`),

  activityDigest: (week?: string, userId?: string) =>
    request<DigestOut>(`/activity/digest${qs({ week, user_id: userId })}`),
};

export const exportPath = (
  format: "csv" | "pdf",
  params: Record<string, string | number | boolean | undefined | null>,
): string => `/export/interactions${qs({ ...params, format })}`;

/** The weekly digest's CSV export. */
export const digestExportPath = (week?: string, userId?: string): string =>
  `/export/digest${qs({ week, user_id: userId, format: "csv" })}`;
