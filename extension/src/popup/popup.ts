// Popup: the employee-facing transparency surface.
// Three states: signed out → consent prompt → monitoring active.

import { api, getApiBase, getToken, isLoopbackBase } from "../api/client";
import type { StatusResponse } from "../shared/types";

const $ = <T extends HTMLElement>(sel: string): T => document.querySelector(sel) as T;

const views = {
  loading: $("#view-loading"),
  login: $("#view-login"),
  consent: $("#view-consent"),
  active: $("#view-active"),
};

// Single source of truth for where the dashboard lives. Baked in at build
// time (PUBLIC_DASHBOARD_URL) so a shared build opens YOUR hosted dashboard.
// An unstamped build must still not send people to a dead localhost: when the
// extension is talking to a hosted backend, the dashboard is that same origin.
// Only a genuinely local API falls back to the Vite dev server.
async function resolveDashboardUrl(): Promise<string> {
  if (__PUBLIC_DASHBOARD_URL__) return __PUBLIC_DASHBOARD_URL__.replace(/\/+$/, "");
  try {
    const base = await getApiBase();
    if (!isLoopbackBase(base)) return new URL(base).origin;
  } catch {
    /* fall through to the dev default */
  }
  return "http://localhost:5173";
}

function show(name: keyof typeof views): void {
  Object.entries(views).forEach(([key, el]) => el.classList.toggle("hidden", key !== name));
}

function setDot(state: "on" | "off" | "warn"): void {
  const dot = $("#status-dot");
  dot.className = `dot ${state}`;
}

function error(sel: string, message: string | null): void {
  const el = $(sel);
  el.textContent = message;
  el.classList.toggle("hidden", !message);
}

async function send<T = Record<string, unknown>>(msg: Record<string, unknown>): Promise<T> {
  const resp = (await chrome.runtime.sendMessage(msg)) as T & { error?: string };
  if (resp && typeof resp === "object" && "error" in resp && resp.error) {
    throw new Error(resp.error);
  }
  return resp;
}

async function refresh(): Promise<void> {
  error("#login-error", null);
  error("#consent-error", null);

  let status: StatusResponse;
  try {
    status = await send<StatusResponse>({ type: "status" });
  } catch (err) {
    show("login");
    setDot("off");
    error("#login-error", `Extension background error: ${(err as Error).message}`);
    return;
  }

  $("#footer-api").textContent = status.apiBase.replace(/^https?:\/\//, "");
  $("#footer-version").textContent = `v${chrome.runtime.getManifest().version}`;

  if (!status.authed) {
    show("login");
    setDot("off");
    return;
  }
  if (!status.consented) {
    show("consent");
    setDot("warn");
    $("#consent-version").textContent = `Policy version: ${status.consentVersion ?? "unknown"}`;
    return;
  }

  show("active");
  setDot("on");
  $("#active-sub").textContent = `${status.user?.full_name ?? ""} · ${status.user?.email ?? ""}`;
  $("#stat-queued").textContent = String(status.queued);
  void renderDiagnostics(); // header line + log are fresh on open

  try {
    const usage = await api.usage(1);
    $("#stat-total").textContent = String(usage.totals.interactions);
    $("#stat-flagged").textContent = String(usage.totals.flagged);
  } catch {
    $("#stat-total").textContent = "–";
    $("#stat-flagged").textContent = "–";
  }
}

/* ------------------------------ event wiring ------------------------------ */

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const btn = $("#login-btn") as HTMLButtonElement;
  btn.disabled = true;
  btn.textContent = "Signing in…";
  try {
    await send({
      type: "login",
      email: $<HTMLInputElement>("#email").value.trim(),
      password: $<HTMLInputElement>("#password").value,
    });
    await refresh();
  } catch (err) {
    error("#login-error", (err as Error).message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Sign in";
  }
});

$("#consent-btn").addEventListener("click", async () => {
  const btn = $("#consent-btn") as HTMLButtonElement;
  btn.disabled = true;
  btn.textContent = "Enabling…";
  try {
    await send({ type: "consent" });
    await refresh();
  } catch (err) {
    error("#consent-error", (err as Error).message);
  } finally {
    btn.disabled = false;
    btn.textContent = "I understand — enable monitoring";
  }
});

$("#dashboard-btn").addEventListener("click", async () => {
  // Hand THIS popup's session to the dashboard via a URL fragment (never
  // sent to the server, stripped from the URL on load). Without it the
  // website opens as whichever account was last signed in there — e.g. the
  // admin — instead of the user looking at the popup right now.
  const dashboard = await resolveDashboardUrl();
  const token = await getToken();
  const url = token
    ? `${dashboard}/#ext_token=${encodeURIComponent(token)}`
    : dashboard;
  void chrome.tabs.create({ url });
});

// No sign-up inside the popup — account creation lives on the dashboard.
$("#register-link").addEventListener("click", () => {
  void resolveDashboardUrl().then((dashboard) =>
    chrome.tabs.create({ url: `${dashboard}/register` }),
  );
});

$("#logout-btn").addEventListener("click", async () => {
  await send({ type: "logout" });
  await refresh();
});

/* ------------------------ tracking diagnostics --------------------------- */
// The background sessionizer keeps a bounded state-transition log in
// chrome.storage.local (ground truth when browser-time numbers look wrong).
// Rendering it here means an anomaly — stuck segment, never-advancing active
// time, queue not draining — is diagnosable from the popup alone, without
// devtools or backend access.

const DEBUG_LOG_KEY = "time_debug_log";
const OPEN_SEGMENT_KEY = "time_open_segment";
const TIME_QUEUE_KEY = "time_queue";

interface DebugEntry {
  t: string;
  event: string;
  osState?: string;
  windowFocused?: boolean;
  kind?: string | null;
  domain?: string | null;
  [extra: string]: unknown;
}

interface OpenSegmentSnapshot {
  kind: "tab" | "away";
  domain: string | null;
  startedAtMs: number;
  activeMs: number;
  idleMs: number;
}

function fmtSpan(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  if (m >= 60) return `${Math.floor(m / 60)}h ${m % 60}m`;
  return m ? `${m}m ${s}s` : `${s}s`;
}

function describeEntry(e: DebugEntry): string {
  const bits: string[] = [];
  if (e.osState) bits.push(`os=${e.osState}`);
  if (e.windowFocused === false) bits.push("window unfocused");
  if (e.kind) bits.push(e.kind);
  if (e.domain) bits.push(e.domain);
  if (typeof e.active_s === "number") {
    bits.push(`${e.active_s}s active · ${typeof e.idle_s === "number" ? e.idle_s : 0}s idle`);
  }
  return bits.join(" · ");
}

async function renderDiagnostics(): Promise<void> {
  try {
    const stored = await chrome.storage.local.get(DEBUG_LOG_KEY);
    const all = (stored[DEBUG_LOG_KEY] as DebugEntry[] | undefined) ?? [];
    const entries = [...all].reverse(); // newest first

    const log = $("#diag-log");
    log.replaceChildren();
    for (const e of entries) {
      const li = document.createElement("li");
      const t = document.createElement("span");
      t.className = "t";
      t.textContent = new Date(e.t).toLocaleTimeString([], { hour12: false });
      const ev = document.createElement("span");
      ev.className = "ev";
      ev.textContent = e.event;
      const meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = describeEntry(e);
      li.append(t, ev, meta);
      log.append(li);
    }
    $("#diag-empty").classList.toggle("hidden", entries.length > 0);

    let waiting = "";
    try {
      const q = await chrome.storage.local.get(TIME_QUEUE_KEY);
      const n = ((q[TIME_QUEUE_KEY] as unknown[] | undefined) ?? []).length;
      if (n) waiting = ` · ${n} segment${n === 1 ? "" : "s"} waiting to upload`;
    } catch {
      /* queue count is supplementary */
    }
    $("#diag-head").textContent = entries.length
      ? `${entries.length} transition${entries.length === 1 ? "" : "s"}${waiting}`
      : `nothing recorded yet${waiting}`;

    const live = $("#diag-live");
    try {
      const sess = await chrome.storage.session.get(OPEN_SEGMENT_KEY);
      const seg = (sess[OPEN_SEGMENT_KEY] as OpenSegmentSnapshot | undefined) ?? null;
      live.textContent = seg
        ? `live: ${seg.kind}${seg.domain ? ` · ${seg.domain}` : ""} · open ${fmtSpan(Date.now() - seg.startedAtMs)} · active ${fmtSpan(seg.activeMs)} · idle ${fmtSpan(seg.idleMs)}`
        : "no open segment right now";
    } catch {
      live.textContent = "open segment unavailable";
    }
  } catch {
    /* diagnostics are best-effort — never break the popup */
  }
}

// Re-render whenever the section is expanded so it reflects the latest state.
$("#diag").addEventListener("toggle", () => {
  if ($<HTMLDetailsElement>("#diag").open) void renderDiagnostics();
});

$("#diag-copy").addEventListener("click", async () => {
  const btn = $("#diag-copy") as HTMLButtonElement;
  try {
    const stored = await chrome.storage.local.get(DEBUG_LOG_KEY);
    await navigator.clipboard.writeText(JSON.stringify(stored[DEBUG_LOG_KEY] ?? [], null, 2));
    btn.textContent = "Copied";
  } catch {
    btn.textContent = "Copy failed";
  }
  setTimeout(() => {
    btn.textContent = "Copy log";
  }, 1500);
});

$("#diag-clear").addEventListener("click", async () => {
  await chrome.storage.local.remove(DEBUG_LOG_KEY);
  await renderDiagnostics();
});

void refresh();
