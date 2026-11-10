// Browser time sessionizer — the workforce-activity layer.
//
// What it records: which URL had the focused tab, split into OS-active vs
// OS-idle seconds, plus whether the tab was playing audio. Nothing else —
// NEVER keystrokes, NEVER page content, and URLs are stripped to
// origin+path (no query strings, no fragments) before anything is queued.
//
// MV3 LIFECYCLE — the critical constraint this file is written around:
// the service worker is suspended after ~30s of quiet and restarted by the
// next event or alarm. A restart re-runs top-level code but does NOT re-fire
// onInstalled/onStartup. Therefore:
//   * listeners are registered at TOP LEVEL (every SW evaluation re-adds
//     them — the previous instance's listeners died with it),
//   * OS-input/focus state is re-seeded from the real values on every start,
//   * the open segment is persisted to chrome.storage.session each tick, so
//     a suspension can no longer silently drop the in-progress segment.
//
// kind semantics (mirrors backend/app/models/activity.py):
//   "tab":  browser focused on this URL → active/idle split from chrome.idle
//   "away": browser unfocused or locked → active = another app was being
//           used, idle = truly away from the keyboard

import { api, ApiError, getToken, getStoredUser } from "../api/client";
import { getDeviceId } from "./device";
import type { TimeSegmentEvent } from "../shared/types";

export const ACTIVITY_TICK_ALARM = "activity-tick";
export const ACTIVITY_FLUSH_ALARM = "activity-time-flush";

const TIME_QUEUE_KEY = "time_queue";
const OPEN_SEGMENT_KEY = "time_open_segment"; // chrome.storage.session
const DEBUG_LOG_KEY = "time_debug_log"; // chrome.storage.local, bounded
const TIME_CAP = 720; // ~12h of closed segments — beyond that, drop oldest
const TIME_BATCH = 100;
const IDLE_DETECTION_SECONDS = 300; // "away" after 5 min with no input
// Accrual is capped per tick so a long service-worker gap can't fabricate
// time: a gap we slept through accrues at most this much (honest undercount).
const MAX_ACCRUAL_MS = 120_000;
const MIN_SEGMENT_MS = 1_000; // sub-second segments are noise
const FOCUS_SETTLE_MS = 400; // transient WINDOW_ID_NONE debounce

interface OpenSegment {
  kind: "tab" | "away";
  domain: string | null;
  path: string | null;
  startedAtMs: number;
  lastTickMs: number;
  activeMs: number;
  idleMs: number;
  audibleMs: number;
  audible: boolean;
}

let current: OpenSegment | null = null;
let windowFocused = true;
let osState: "active" | "idle" | "locked" = "active";
const audibleTabs = new Set<number>();
let initialized = false;
let focusCheckTimer: number | null = null;

/** Bounded transition log — ground truth when numbers look wrong. */
function logState(event: string, extra?: Record<string, unknown>): void {
  void (async () => {
    try {
      const stored = await chrome.storage.local.get(DEBUG_LOG_KEY);
      const log = (stored[DEBUG_LOG_KEY] as unknown[] | undefined) ?? [];
      log.push({
        t: new Date().toISOString(),
        event,
        osState,
        windowFocused,
        kind: current?.kind ?? null,
        ...extra,
      });
      await chrome.storage.local.set({ [DEBUG_LOG_KEY]: log.slice(-40) });
    } catch {
      /* diagnostics only — never break tracking */
    }
  })();
}

async function consented(): Promise<boolean> {
  const user = await getStoredUser();
  return !!user?.consent_accepted && !!user?.is_enrolled;
}

/** origin+path only — query strings and fragments never leave the device. */
function sanitizeUrl(raw: string | undefined): { domain: string | null; path: string | null } {
  if (!raw) return { domain: null, path: null };
  try {
    const url = new URL(raw);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return { domain: null, path: null }; // chrome://, extension pages, files
    }
    return {
      domain: url.host.toLowerCase().replace(/^www\./, ""),
      path: (url.pathname || "/").slice(0, 512),
    };
  } catch {
    return { domain: null, path: null };
  }
}

type Desired = { kind: "tab" | "away"; domain: string | null; path: string | null; audible: boolean };

async function desiredState(): Promise<Desired> {
  if (!windowFocused || osState === "locked") {
    return { kind: "away", domain: null, path: null, audible: false };
  }
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab) return { kind: "away", domain: null, path: null, audible: false };
  const { domain, path } = sanitizeUrl(tab.url);
  // Focused but OS-idle (user walked away leaving the browser open): time
  // still belongs to this page, accrued as idle by accrue().
  return { kind: "tab", domain, path, audible: audibleTabs.has(tab.id ?? -1) };
}

function accrue(now: number): void {
  if (!current) return;
  const elapsed = Math.min(Math.max(now - current.lastTickMs, 0), MAX_ACCRUAL_MS);
  current.lastTickMs = now;
  const inputRecent = windowFocused && osState === "active";
  if (inputRecent) current.activeMs += elapsed;
  else current.idleMs += elapsed;
  // Media playing is consumption even without input — accrue it either way.
  if (current.kind === "tab" && current.audible) current.audibleMs += elapsed;
}

async function persistOpen(): Promise<void> {
  try {
    if (current) await chrome.storage.session.set({ [OPEN_SEGMENT_KEY]: current });
    else await chrome.storage.session.remove([OPEN_SEGMENT_KEY]);
  } catch {
    /* storage unavailable — tracking still works within this SW lifetime */
  }
}

async function restoreOpen(): Promise<void> {
  try {
    const stored = await chrome.storage.session.get(OPEN_SEGMENT_KEY);
    const saved = stored[OPEN_SEGMENT_KEY] as OpenSegment | null;
    if (!saved) return;
    // Never credit the suspended gap — clamp the clock forward (undercount).
    saved.lastTickMs = Date.now();
    current = saved;
    logState("segment-restored", { domain: saved.domain });
  } catch {
    /* start fresh */
  }
}

function closeSegment(): void {
  if (!current) return;
  const seg = current;
  current = null;
  void persistOpen();
  const totalMs = seg.activeMs + seg.idleMs;
  if (totalMs < MIN_SEGMENT_MS) return;
  void enqueue({
    client_event_id: crypto.randomUUID(),
    kind: seg.kind,
    domain: seg.domain,
    page_path: seg.path,
    active_seconds: Math.round(seg.activeMs / 1000),
    idle_seconds: Math.round(seg.idleMs / 1000),
    audible_seconds: Math.round(seg.audibleMs / 1000),
    started_at: new Date(seg.startedAtMs).toISOString(),
    ended_at: new Date(Date.now()).toISOString(),
  });
  logState("segment-closed", { domain: seg.domain, active_s: Math.round(seg.activeMs / 1000), idle_s: Math.round(seg.idleMs / 1000) });
}

/** Bring the open segment in line with reality; called on every transition. */
export async function activityRefresh(): Promise<void> {
  if (!(await consented())) {
    closeSegment(); // consent withdrawn / logged out → stop accruing
    return;
  }
  const desired = await desiredState();
  const now = Date.now();
  if (current) {
    accrue(now);
    if (
      current.kind === desired.kind &&
      current.domain === desired.domain &&
      current.path === desired.path
    ) {
      current.audible = desired.audible;
      await persistOpen();
      return; // same segment continues
    }
    closeSegment();
  }
  current = {
    kind: desired.kind,
    domain: desired.domain,
    path: desired.path,
    startedAtMs: now,
    lastTickMs: now,
    activeMs: 0,
    idleMs: 0,
    audibleMs: 0,
    audible: desired.audible,
  };
  await persistOpen();
  logState("segment-opened", { kind: desired.kind, domain: desired.domain });
}

/* ----------------------------- queue + flush ------------------------------ */

let timeQueueLock: Promise<unknown> = Promise.resolve();
function serialized<T>(op: () => Promise<T>): Promise<T> {
  const run = timeQueueLock.then(op, op);
  timeQueueLock = run.catch(() => undefined);
  return run;
}

async function enqueue(event: TimeSegmentEvent): Promise<void> {
  await serialized(async () => {
    const stored = await chrome.storage.local.get(TIME_QUEUE_KEY);
    const queue = (stored[TIME_QUEUE_KEY] as TimeSegmentEvent[] | undefined) ?? [];
    queue.push(event);
    await chrome.storage.local.set({ [TIME_QUEUE_KEY]: queue.slice(-TIME_CAP) });
  });
}

let timeFlushTimer: number | null = null;
function scheduleTimeFlush(): void {
  if (timeFlushTimer !== null) return;
  timeFlushTimer = self.setTimeout(() => {
    timeFlushTimer = null;
    void flushTimeQueue();
  }, 3000);
}

export async function flushTimeQueue(): Promise<void> {
  if (!(await getToken())) return;
  await serialized(async () => {
    const stored = await chrome.storage.local.get(TIME_QUEUE_KEY);
    const queue = (stored[TIME_QUEUE_KEY] as TimeSegmentEvent[] | undefined) ?? [];
    if (!queue.length) return;

    const batch = queue.slice(0, TIME_BATCH);
    try {
      const resp = await api.timeSessions(await getDeviceId(), batch);
      if (resp.rejected?.length) {
        console.warn("[Sentinel] backend rejected", resp.rejected.length, "time segment(s):", resp.rejected);
      }
      // Remove exactly the posted events — never a stale snapshot.
      const posted = new Set(batch.map((e) => e.client_event_id));
      const remaining = queue.filter((e) => !posted.has(e.client_event_id));
      await chrome.storage.local.set({ [TIME_QUEUE_KEY]: remaining });
      if (remaining.length) scheduleTimeFlush();
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        return; // session/consent problem — queue is preserved for after re-login
      }
      scheduleTimeFlush();
    }
  });
}

/** Alarm tick: accrue what happened since the last tick, then re-sync state. */
export async function activityTick(): Promise<void> {
  accrue(Date.now());
  await persistOpen();
  await activityRefresh();
}

/* ------------------------------- wiring ----------------------------------- */

function setWindowFocused(focused: boolean): void {
  if (windowFocused === focused) return;
  windowFocused = focused;
  logState("focus", { focused });
  void activityRefresh();
}

export async function initActivityTracker(): Promise<void> {
  if (initialized) return; // one init per service-worker instance
  initialized = true;

  chrome.idle.onStateChanged.addListener((state) => {
    osState = state as typeof osState;
    logState("os-state", { state });
    void activityRefresh();
  });
  chrome.windows.onFocusChanged.addListener((windowId) => {
    if (windowId === chrome.windows.WINDOW_ID_NONE) {
      // Chrome fires a transient NONE for popups/menus before the real
      // focus event — debounce and confirm before committing an away.
      if (focusCheckTimer !== null) self.clearTimeout(focusCheckTimer);
      focusCheckTimer = self.setTimeout(() => {
        focusCheckTimer = null;
        void chrome.windows
          .getLastFocused({ populate: false })
          .then((win) => setWindowFocused(win.focused))
          .catch(() => setWindowFocused(false));
      }, FOCUS_SETTLE_MS);
      return;
    }
    if (focusCheckTimer !== null) {
      self.clearTimeout(focusCheckTimer);
      focusCheckTimer = null;
    }
    setWindowFocused(true);
  });
  chrome.tabs.onActivated.addListener(() => void activityRefresh());
  chrome.tabs.onUpdated.addListener((_tabId, changeInfo, tab) => {
    if (changeInfo.audible !== undefined) {
      if (changeInfo.audible) audibleTabs.add(tab.id ?? -1);
      else audibleTabs.delete(tab.id ?? -1);
    }
    if (changeInfo.url || changeInfo.status === "complete") void activityRefresh();
  });
  chrome.tabs.onRemoved.addListener(() => void activityRefresh());

  // Re-seed from REAL state — defaults are guesses and a restarted SW has
  // no memory of where the user actually is.
  try {
    await chrome.idle.setDetectionInterval(IDLE_DETECTION_SECONDS);
    osState = await chrome.idle.queryState(IDLE_DETECTION_SECONDS);
  } catch {
    /* keep defaults */
  }
  try {
    const win = await chrome.windows.getLastFocused({ populate: false });
    windowFocused = win.focused;
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (tab?.id != null && tab.audible) audibleTabs.add(tab.id);
  } catch {
    /* keep defaults */
  }
  await restoreOpen();
  logState("init");
  await activityRefresh();
}

// TOP-LEVEL init: a restarted MV3 service worker re-runs this file but never
// re-fires onInstalled/onStartup — registering here means listeners and state
// are restored on EVERY wake, which is what keeps active/idle accrual honest.
void initActivityTracker();
