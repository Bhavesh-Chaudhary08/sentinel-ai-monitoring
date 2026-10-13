// API client — every call goes through the background service worker
// (extension fetches with host_permissions → no CORS issues; content scripts
// must never call the backend directly).

import type {
  AiDomainsResponse,
  CaptureEvent,
  CaptureResponse,
  PolicyCheckResponse,
  ShadowVisitEvent,
  ShadowVisitResponse,
  TokenResponse,
  UsageResponse,
  UserOut,
} from "../shared/types";

// Public backend URL baked in at build time by build.mjs (PUBLIC_API_URL);
// empty in dev builds. A shared build therefore points every friend's browser
// at YOUR hosted backend with zero configuration on their side.
const BAKED_API_URL = __PUBLIC_API_URL__.replace(/\/+$/, "");

export const DEFAULT_API_BASE = BAKED_API_URL || "http://localhost:8001/api/v1";  // compose maps API to 8001 (8000 is taken on dev machines)

const TOKEN_KEY = "token";
const USER_KEY = "user";
const API_BASE_KEY = "api_base";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function getApiBase(): Promise<string> {
  const stored = await chrome.storage.local.get(API_BASE_KEY);
  return (stored[API_BASE_KEY] as string) || DEFAULT_API_BASE;
}

export async function setApiBase(base: string): Promise<void> {
  await chrome.storage.local.set({ [API_BASE_KEY]: base.replace(/\/+$/, "") });
}

/** Where the backend might be, beyond the stored base.
 *  Shared build → only the baked-in public URL (never probe a friend's own
 *  localhost). Dev build → 8001 = compose API mapping, 8000 = uvicorn direct. */
export const API_BASE_CANDIDATES = BAKED_API_URL
  ? [DEFAULT_API_BASE]
  : [DEFAULT_API_BASE, "http://localhost:8000/api/v1"];

/**
 * Find a base that actually answers and persist it. Probes the public
 * /meta/ai-domains endpoint (no auth) on each candidate, starting with the
 * currently configured one — an explicit user override in options wins as
 * long as it is reachable. Returns the working base, or null if none respond.
 */
export async function probeApiBase(): Promise<string | null> {
  const stored = await getApiBase();
  const candidates = [stored, ...API_BASE_CANDIDATES.filter((c) => c !== stored)];
  for (const base of candidates) {
    try {
      const resp = await fetch(`${base}/meta/ai-domains`);
      if (resp.ok) {
        if (base !== stored) await setApiBase(base);
        return base;
      }
    } catch {
      /* connection error → try the next candidate */
    }
  }
  return null;
}

export async function getToken(): Promise<string | null> {
  const stored = await chrome.storage.local.get(TOKEN_KEY);
  return (stored[TOKEN_KEY] as string) ?? null;
}

export async function setSession(token: string, user: UserOut): Promise<void> {
  await chrome.storage.local.set({ [TOKEN_KEY]: token, [USER_KEY]: user });
}

export async function clearSession(): Promise<void> {
  await chrome.storage.local.remove([TOKEN_KEY, USER_KEY]);
}

export async function getStoredUser(): Promise<UserOut | null> {
  const stored = await chrome.storage.local.get(USER_KEY);
  return (stored[USER_KEY] as UserOut) ?? null;
}

async function request<T>(
  path: string,
  init: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  const base = await getApiBase();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (init.auth !== false) {
    const token = await getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  let resp: Response;
  try {
    resp = await fetch(`${base}${path}`, { ...init, headers });
  } catch (err) {
    throw new ApiError(0, `Backend unreachable: ${(err as Error).message}`);
  }

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    if (resp.status === 401) await clearSession();
    throw new ApiError(resp.status, detail);
  }
  return (await resp.json()) as T;
}

export const api = {
  login: (email: string, password: string) =>
    // FastAPI's OAuth2PasswordRequestForm expects form encoding, not JSON.
    request<TokenResponse>("/auth/token", {
      method: "POST",
      auth: false,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: email, password }).toString(),
    }),

  me: () => request<UserOut>("/auth/me"),

  consent: (deviceId: string, extensionVersion: string) =>
    request<UserOut>("/auth/consent", {
      method: "POST",
      body: JSON.stringify({
        device_id: deviceId,
        extension_version: extensionVersion,
        accepted: true,
      }),
    }),

  aiDomains: () => request<AiDomainsResponse>("/meta/ai-domains", { auth: false }),

  capture: (deviceId: string, events: CaptureEvent[]) =>
    request<CaptureResponse>("/capture/interactions", {
      method: "POST",
      body: JSON.stringify({ device_id: deviceId, events }),
    }),

  shadowVisits: (deviceId: string, events: ShadowVisitEvent[]) =>
    request<ShadowVisitResponse>("/capture/shadow-visits", {
      method: "POST",
      body: JSON.stringify({ device_id: deviceId, events }),
    }),

  policyCheck: (payload: {
    prompt_text: string;
    ai_tool: string;
    domain: string;
    page_path?: string;
  }) =>
    request<PolicyCheckResponse>("/policy/check", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  usage: (days = 1) => request<UsageResponse>(`/analytics/usage?days=${days}`),
};
