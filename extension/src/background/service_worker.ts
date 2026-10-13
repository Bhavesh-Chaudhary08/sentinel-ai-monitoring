// Background service worker — the ONLY place the extension talks to the backend.
//
// Responsibilities:
//  * durable capture queue (chrome.storage.session survives SW suspension),
//  * batched, retrying flush to POST /capture/interactions,
//  * auth/consent state machine (login → consent → enrolled),
//  * shadow-AI probe on unknown hosts (markers only — never page content),
//  * dynamic content-script registration for newly-allowed domains,
//  * always-visible badge state on AI tabs.

import { api, ApiError, getApiBase, getStoredUser, getToken, probeApiBase, setApiBase, setSession, clearSession } from "../api/client";
import { FALLBACK_KNOWN_DOMAINS, matchesDomain, normalizeHost } from "../rules/known-domains";
import type { AiTool, CaptureEvent, CaptureResponse, ShadowVisitEvent, StatusResponse, UserOut } from "../shared/types";

const QUEUE_KEY = "queue";
const DOMAIN_CACHE_KEY = "domain_cache";
const EXTRA_DOMAINS_KEY = "extra_domains";
const DEVICE_ID_KEY = "device_id";
const DYN_PREFIX = "aidlp-dyn-";
const QUEUE_CAP = 500;
const BATCH_SIZE = 50;

const EXT_VERSION = chrome.runtime.getManifest().version;

/** Domains covered by manifest.json's static content_scripts (don't double-register). */
const STATIC_DOMAINS = new Set([
  "chatgpt.com",
  "chat.openai.com",
  "gemini.google.com",
  "claude.ai",
  "copilot.microsoft.com",
  "github.com",
  "perplexity.ai",
  "poe.com",
]);

/* ---------------- known-domain list (backend is source of truth) ---------- */

async function getKnownDomains(force = false): Promise<string[]> {
  const stored = await chrome.storage.local.get([DOMAIN_CACHE_KEY, EXTRA_DOMAINS_KEY]);
  const cache = stored[DOMAIN_CACHE_KEY] as { fetched_at: number; domains: string[] } | undefined;
  const extra = (stored[EXTRA_DOMAINS_KEY] as string[] | undefined) ?? [];

  let base = cache?.domains?.length ? cache.domains : FALLBACK_KNOWN_DOMAINS;
  if (!force && cache && Date.now() - cache.fetched_at < 6 * 3600_000) {
    return Array.from(new Set([...base, ...extra]));
  }
  try {
    const resp = await api.aiDomains();
    base = Array.from(new Set([...FALLBACK_KNOWN_DOMAINS, ...resp.domains]));
    await chrome.storage.local.set({ [DOMAIN_CACHE_KEY]: { fetched_at: Date.now(), domains: base } });
  } catch {
    /* offline → keep cached/fallback */
  }
  return Array.from(new Set([...base, ...extra]));
}

/* ------------------------------- queue ------------------------------------ */

/**
 * All queue reads/writes are serialized: enqueue is a read-modify-write with
 * awaits in between, and capture messages arrive in bursts (prompt + response
 * mutations). Without the lock, concurrent enqueues all read the same base
 * queue and the last writer wins — silently dropping the events the earlier
 * writers added (empirically: the prompt, emitted first, always lost).
 */
let queueLock: Promise<unknown> = Promise.resolve();
function serialized<T>(op: () => Promise<T>): Promise<T> {
  const run = queueLock.then(op, op);
  queueLock = run.catch(() => undefined);
  return run;
}

async function enqueue(event: CaptureEvent): Promise<void> {
  await serialized(async () => {
    const stored = await chrome.storage.local.get(QUEUE_KEY);
    const queue = (stored[QUEUE_KEY] as CaptureEvent[] | undefined) ?? [];
    queue.push(event);
    await chrome.storage.local.set({ [QUEUE_KEY]: queue.slice(-QUEUE_CAP) });
    if (queue.length >= BATCH_SIZE) void flushQueue();
    else scheduleFlush();
  });
}

let flushTimer: number | null = null;
function scheduleFlush(): void {
  if (flushTimer !== null) return;
  flushTimer = self.setTimeout(() => {
    flushTimer = null;
    void flushQueue();
  }, 3000);
}

async function flushQueue(): Promise<void> {
  if (!(await getToken())) return;
  await serialized(async () => {
    const stored = await chrome.storage.local.get(QUEUE_KEY);
    const queue = (stored[QUEUE_KEY] as CaptureEvent[] | undefined) ?? [];
    if (!queue.length) return;

    const batch = queue.slice(0, BATCH_SIZE);
    try {
      const deviceId = await getDeviceId();
      const resp = await api.capture(deviceId, batch);
      if (resp.rejected?.length) {
        console.warn("[Sentinel] backend rejected", resp.rejected.length, "event(s):", resp.rejected);
      }
      // Remove exactly the posted events from the CURRENT queue — never slice
      // a stale snapshot (anything enqueued mid-flight would be clobbered).
      const posted = new Set(batch.map((e) => e.client_event_id));
      const remaining = queue.filter((e) => !posted.has(e.client_event_id));
      await chrome.storage.local.set({ [QUEUE_KEY]: remaining });
      if (remaining.length) scheduleFlush();
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        return; // session/consent problem — popup surfaces it; queue is preserved
      }
      scheduleFlush(); // network hiccup → retry with a short backoff
    }
  });
}

async function getDeviceId(): Promise<string> {
  const stored = await chrome.storage.local.get(DEVICE_ID_KEY);
  const existing = stored[DEVICE_ID_KEY] as string | undefined;
  if (existing) return existing;
  const id = `ext-${crypto.randomUUID()}`;
  await chrome.storage.local.set({ [DEVICE_ID_KEY]: id });
  return id;
}

/* --------------------------- shadow-AI probe ------------------------------ */

/** Runs inside the page (serializable — no closures over extension scope). */
function probePage(): { markers: Record<string, boolean>; title: string } {
  const body = (document.body?.innerText || "").slice(0, 6000).toLowerCase();
  const composer = !!document.querySelector(
    "textarea, [contenteditable='true'], rich-textarea",
  );
  const sendLabel = Array.from(
    document.querySelectorAll("button, [role='button'], input[type='submit']"),
  ).some((el) => {
    const text = ((el as HTMLElement).innerText || (el as HTMLInputElement).value || "").trim();
    return /^(send|submit|send message|send prompt)( message)?$/i.test(text);
  });
  const chatWords = /\b(chat|assistant|ask ai|ai response|prompt)\b/.test(body);
  return {
    markers: { composer, send_label: sendLabel, chat_words: chatWords },
    title: (document.title || "").slice(0, 120),
  };
}

async function handleNavigation(tabId: number, url: string): Promise<void> {
  let host: string;
  try {
    host = normalizeHost(new URL(url).host);
  } catch {
    return;
  }
  if (!host) return;

  const domains = await getKnownDomains();
  if (domains.some((d) => matchesDomain(host, d))) {
    await setBadge(tabId, "ON", "#16a34a");
    return;
  }

  // Unknown host: only probe when this profile is enrolled AND consented —
  // unenrolled users generate zero network traffic from this extension.
  const user = await getStoredUser();
  if (!user?.consent_accepted || !user?.is_enrolled) return;

  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: probePage,
    });
    const probe = results?.[0]?.result as ReturnType<typeof probePage> | undefined;
    if (!probe) return;
    const found = Object.values(probe.markers).some(Boolean);
    if (!found) return; // doesn't look like a chat product → nothing leaves the device

    const event: ShadowVisitEvent = {
      client_event_id: crypto.randomUUID(),
      occurred_at: new Date().toISOString(),
      domain: host,
      page_title: probe.title,
      markers: probe.markers,
    };
    const deviceId = await getDeviceId();
    const resp = await api.shadowVisits(deviceId, [event]);

    const allowed = Array.from(new Set([...resp.first_seen, ...resp.capture_enabled_for]));
    if (allowed.length) {
      await syncDynamicScripts();
      // Capture can start immediately for this tab too (registered scripts only
      // apply to future navigations).
      await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
      await setBadge(tabId, "ON", "#16a34a");
    }
  } catch {
    /* protected pages / closed tab — ignore */
  }
}

/* ------------------- dynamic content-script registration ------------------ */

async function syncDynamicScripts(): Promise<void> {
  const user = await getStoredUser();
  const owned = async () => {
    const all = await chrome.scripting.getRegisteredContentScripts();
    return all.filter((s) => s.id.startsWith(DYN_PREFIX));
  };

  if (!user?.consent_accepted || !user?.is_enrolled) {
    const toRemove = (await owned()).map((s) => s.id);
    if (toRemove.length) await chrome.scripting.unregisterContentScripts({ ids: toRemove });
    return;
  }

  const want = new Map<string, string[]>();
  for (const domain of await getKnownDomains()) {
    if (STATIC_DOMAINS.has(domain)) continue;
    const id = DYN_PREFIX + domain.replace(/[^a-z0-9.-]/gi, "_");
    want.set(id, [`*://${domain}/*`, `*://*.${domain}/*`]);
  }

  const current = await owned();
  const currentIds = new Set(current.map((s) => s.id));
  const removeIds = current.filter((s) => !want.has(s.id)).map((s) => s.id);
  if (removeIds.length) await chrome.scripting.unregisterContentScripts({ ids: removeIds });

  const toAdd = Array.from(want.entries())
    .filter(([id]) => !currentIds.has(id))
    .map(([id, matches]) => ({
      id,
      matches,
      js: ["content.js"],
      runAt: "document_idle" as const,
      allFrames: false,
      persistAcrossSessions: true,
    }));
  if (toAdd.length) await chrome.scripting.registerContentScripts(toAdd);
}

/* ------------------------------ badge ------------------------------------- */

async function setBadge(tabId: number, text: string, color: string): Promise<void> {
  try {
    await chrome.action.setBadgeBackgroundColor({ tabId, color });
    await chrome.action.setBadgeText({ tabId, text });
  } catch {
    /* tab went away */
  }
}

/* ------------------------------ messaging --------------------------------- */

async function handleMessage(msg: Record<string, unknown>): Promise<unknown> {
  switch (msg.type) {
    case "status": {
      const user = await getStoredUser();
      const stored = await chrome.storage.local.get(QUEUE_KEY);
      const queued = ((stored[QUEUE_KEY] as CaptureEvent[] | undefined) ?? []).length;
      return {
        authed: !!user,
        consented: !!user?.consent_accepted,
        enrolled: !!user?.is_enrolled,
        user,
        queued,
        apiBase: await getApiBase(),
        consentVersion: user?.consent_version ?? null,
      } satisfies StatusResponse;
    }
    case "login": {
      let resp: Awaited<ReturnType<typeof api.login>>;
      try {
        resp = await api.login(String(msg.email), String(msg.password));
      } catch (err) {
        // Connection failure — the configured base may be stale (e.g. backend
        // running on the dev port instead of the compose mapping). Probe for
        // a reachable one and retry once.
        if (!(err instanceof ApiError) || err.status !== 0) throw err;
        if (!(await probeApiBase())) throw err;
        resp = await api.login(String(msg.email), String(msg.password));
      }
      // Store the token first — the consent call below needs it as Bearer auth.
      await setSession(resp.access_token, resp.user);
      // Re-assert consent and bind THIS device on every login. The backend only
      // accepts capture from the device_id bound to the account, so a user who
      // was seeded/enrolled elsewhere must be re-bound to the browser they
      // actually log in from — otherwise every capture would 403.
      const bound = await api.consent(await getDeviceId(), EXT_VERSION);
      await setSession(resp.access_token, bound);
      await getKnownDomains(true);
      await syncDynamicScripts();
      void flushQueue();
      return { ok: true, user: resp.user };
    }
    case "consent": {
      const deviceId = await getDeviceId();
      const user: UserOut = await api.consent(deviceId, EXT_VERSION);
      const token = await getToken();
      if (token) await setSession(token, user);
      await syncDynamicScripts();
      void flushQueue();
      return { ok: true, user };
    }
    case "logout": {
      await clearSession();
      const all = await chrome.scripting.getRegisteredContentScripts();
      const dyn = all.filter((s) => s.id.startsWith(DYN_PREFIX)).map((s) => s.id);
      if (dyn.length) await chrome.scripting.unregisterContentScripts({ ids: dyn });
      return { ok: true };
    }
    case "preflight": {
      try {
        return await api.policyCheck({
          prompt_text: String(msg.prompt),
          ai_tool: String(msg.tool) as AiTool,
          domain: String(msg.domain),
          page_path: msg.pagePath ? String(msg.pagePath) : undefined,
        });
      } catch {
        // Fail OPEN (send allowed) but keep it visible: capture+classification
        // still runs post-hoc when the backend is reachable again.
        return {
          action: "log_only",
          message: null,
          category: "none",
          confidence: 0,
          flagged: false,
          rule_id: null,
          rule_name: null,
        };
      }
    }
    case "capture":
      await enqueue(msg.event as CaptureEvent);
      return { ok: true };
    case "setApiBase":
      await setApiBase(String(msg.base));
      await getKnownDomains(true);
      await syncDynamicScripts();
      return { ok: true, apiBase: await getApiBase() };
    case "resync":
      await getKnownDomains(true);
      await syncDynamicScripts();
      return { ok: true, domains: await getKnownDomains() };
    default:
      return { error: "unknown message type" };
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  handleMessage(msg as Record<string, unknown>)
    .then(sendResponse)
    .catch((err: unknown) =>
      sendResponse({ error: err instanceof Error ? err.message : String(err) }),
    );
  return true; // keep the channel open for the async reply
});

/* ------------------------------ lifecycle --------------------------------- */

chrome.runtime.onInstalled.addListener(() => {
  // Probe picks whichever backend actually answers (compose 8001 / direct
  // 8000), rewriting a stale stored base if needed — this subsumes the old
  // hardcoded "8000 → 8001" migration, which raced the probe on every install.
  // Then refreshes the domain list from the reachable backend.
  void probeApiBase().then(() => getKnownDomains(true)).then(syncDynamicScripts);
  void chrome.alarms.create("flush-queue", { periodInMinutes: 0.5 });
});

chrome.runtime.onStartup.addListener(() => {
  void probeApiBase().then(syncDynamicScripts);
  void chrome.alarms.create("flush-queue", { periodInMinutes: 0.5 });
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "flush-queue") void flushQueue();
});

chrome.webNavigation.onCompleted.addListener((details) => {
  if (details.frameId !== 0) return;
  void handleNavigation(details.tabId, details.url);
});

// Tab switches must refresh the visible indicator immediately.
chrome.tabs.onActivated.addListener(async (activeInfo) => {
  try {
    const tab = await chrome.tabs.get(activeInfo.tabId);
    if (tab.url) await handleNavigation(activeInfo.tabId, tab.url);
  } catch {
    /* ignore */
  }
});
