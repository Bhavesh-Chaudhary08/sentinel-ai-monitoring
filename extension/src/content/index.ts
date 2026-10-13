// Content script entry — capture layer only. PROMPTS-ONLY by design:
// responses are detected (they trigger prompt pairing) but their text is never
// sent to the backend or shown anywhere.
// Rules of the road:
//  * never blocks or reshapes page behavior except DLP pre-flight interception,
//  * emits messages to the background queue; all networking lives there,
//  * first snapshot is a baseline (page history is NOT re-uploaded on load).

import { getAdapter, type SiteAdapter, type CollectedMessage } from "./adapters";
import { showOverlay } from "./overlay";
import type { CaptureEvent } from "../shared/types";

declare global {
  interface Window {
    __aidlpInjected?: boolean;
    __aidlpEmitted?: Set<string>;
    __aidlpScanned?: boolean;
  }
}

// Guard against double injection (static manifest match + dynamic registration
// + manual scripting.executeScript can all race on shadow-AI domains).
if (!window.__aidlpInjected) {
  window.__aidlpInjected = true;
  main();
}

function main(): void {
  const adapter = getAdapter(location.host);
  const seen = new Set<string>();
  let firstSnapshot = true;
  let debounceTimer: number | null = null;

  const scan = () => {
    const messages = adapter.collect();
    if (messages.length && !window.__aidlpScanned) {
      window.__aidlpScanned = true;
      console.info(`[Sentinel] scan ok: ${messages.filter((m) => m.role === "assistant").length} assistant element(s) found`);
    }
    for (const m of messages) {
      const key = fingerprint(m);
      if (seen.has(key)) continue;
      seen.add(key);
      if (!m.text.trim()) continue;
      if (m.role === "user") {
        // Prefer the text armed at send time — it is the verbatim prompt even
        // when site markup wraps/truncates the rendered version. A prompt that
        // was JUST sent is not "history", so it emits even on the baseline run.
        const armed = takePendingPrompt();
        if (armed) {
          emitUser(armed, "send-time arming");
          continue;
        }
      }
      // Baseline run seeds `seen` without emitting (no replaying old history).
      if (!firstSnapshot) emitOnce(m);
    }
    // Bound memory on very long sessions.
    if (seen.size > 600) {
      const keep = new Set(Array.from(seen).slice(-300));
      seen.clear();
      for (const k of keep) seen.add(k);
    }
    firstSnapshot = false;
  };

  const onMutation = () => {
    if (debounceTimer !== null) window.clearTimeout(debounceTimer);
    // 500ms: coalesces React/Vue re-render bursts. characterData is deliberately
    // off so token-by-streaming updates don't emit half-finished responses —
    // completion buttons/toolbars trigger a childList mutation with final text.
    debounceTimer = window.setTimeout(scan, 500);
  };

  // Safety net: if the site's DOM never yields a user-message element the
  // adapter recognizes (markup drift), the armed prompt would silently expire.
  // Emit it on the next tick after arming regardless of markup.
  const drainTimer = window.setInterval(() => {
    if (!pendingPrompt) return;
    if (Date.now() - pendingPrompt.at < 1_500) return; // give the DOM a beat first
    const text = takePendingPrompt() as string;
    emitUser(text, "drain fallback");
  }, 1_000);
  void drainTimer; // never cleared — page-lifetime watchdog

  console.info(
    `[Sentinel] capture active on ${location.host} · adapter=${adapter.tool} · composer=${
      adapter.composer() ? "found" : "NOT FOUND (arming still works)"
    }`,
  );

  scan(); // baseline (no emits)
  installPreflight(adapter);
  installSendHooks(adapter);
  new MutationObserver(onMutation).observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: false,
  });
}

/** Prompts-only: assistant messages are pairing triggers, never emitted. */
function emitOnce(m: CollectedMessage): void {
  if (m.role === "assistant") {
    // A response appearing means a prompt was just sent: flush the armed
    // (send-hook) or recently-typed text as the prompt, then drop the
    // response content entirely — this project logs prompts, not answers.
    const promptText = pendingPrompt ? takePendingPrompt() : takeLastTyped();
    if (promptText) emitUser(promptText, "paired with response");
    return;
  }
  emitUser(m.text, "dom scan");
}

/** Emit a user prompt exactly once, deduped against every other path. */
function emitUser(text: string, via: string): void {
  const key = fingerprint({ role: "user", text });
  const set = (window.__aidlpEmitted ??= new Set<string>());
  if (set.has(key)) return;
  set.add(key);
  if (set.size > 600) {
    const keep = Array.from(set).slice(-300);
    set.clear();
    for (const k of keep) set.add(k);
  }
  console.info("[Sentinel] prompt captured (", text.length, "chars, via", via + ")");
  emit({ role: "user", text });
}

/* ---------------------- send-time prompt arming --------------------------- */
/**
 * Site markup is an unreliable source for the *exact* prompt (renderers wrap,
 * truncate or split it). So we snapshot the composer text the moment the user
 * sends — Enter key or send-button press — and emit it via scan reconciliation
 * or the drain fallback. Anything older than PROMPT_TTL is discarded so stale
 * arming can never attach to the wrong message.
 */

const PROMPT_TTL_MS = 15_000;
let pendingPrompt: { text: string; at: number } | null = null;

function armPrompt(text: string): void {
  pendingPrompt = { text, at: Date.now() };
}

function takePendingPrompt(): string | null {
  if (!pendingPrompt) return null;
  if (Date.now() - pendingPrompt.at > PROMPT_TTL_MS) {
    pendingPrompt = null;
    return null;
  }
  const text = pendingPrompt.text;
  pendingPrompt = null;
  return text;
}

/* --- input tracking: the third, site-independent capture path ---
 * Records whatever the user types into any editable, continuously. When a
 * response arrives, an un-emitted recent typing is paired as its prompt.
 * This works even when Enter/send-button hooks miss and site markup drifts. */
const LAST_TYPED_TTL_MS = 120_000;
let lastTyped: { text: string; at: number } | null = null;

function noteTyping(text: string): void {
  if (text.trim()) lastTyped = { text, at: Date.now() };
}

function takeLastTyped(): string | null {
  if (!lastTyped) return null;
  if (Date.now() - lastTyped.at > LAST_TYPED_TTL_MS) {
    lastTyped = null;
    return null;
  }
  const text = lastTyped.text;
  lastTyped = null;
  return text;
}

function installSendHooks(adapter: SiteAdapter): void {
  // The arming target is "whatever editable the user is typing in" — NOT the
  // adapter's composer guess. Selectors drift on SPAs; focus does not lie.
  const editableIn = (root: Element | null): Element | null => {
    if (!root) return null;
    return root.closest(
      "textarea, [contenteditable='true'], [contenteditable=''], rich-textarea, .ql-editor, .ProseMirror",
    );
  };
  const textOf = (el: HTMLElement | null): string =>
    !el ? "" : el instanceof HTMLTextAreaElement ? el.value : el.innerText || "";

  // Enter-to-send: capture phase fires before site handlers can clear the box.
  document.addEventListener(
    "keydown",
    (ev) => {
      if (ev.key !== "Enter" || ev.shiftKey || ev.isComposing) return;
      const target = ev.target as HTMLElement | null;
      const editable = editableIn(target) as HTMLElement | null;
      if (!target || !editable) return;
      const text = textOf(editable);
      if (text.trim()) {
        armPrompt(text);
        console.info("[Sentinel] prompt armed via Enter (", text.length, "chars)");
      }
    },
    true,
  );

  // Send-button presses (pointerdown precedes the click that clears the box).
  document.addEventListener(
    "pointerdown",
    (ev) => {
      const btn = (ev.target as HTMLElement | null)?.closest(
        "button, [role='button'], .send-button, [aria-label*='send' i]",
      ) as HTMLElement | null;
      if (!btn) return;
      const label = `${btn.getAttribute("aria-label") ?? ""} ${btn.getAttribute("mattooltip") ?? ""} ${btn.getAttribute("data-test-id") ?? ""}`.toLowerCase();
      const active = document.activeElement as HTMLElement | null;
      const editable = ((active && editableIn(active)) || adapter.composer()) as HTMLElement | null;
      const nearComposer =
        !!editable &&
        (btn.contains(editable) ||
          editable.contains(btn) ||
          (!!(btn.closest("form") && editable.closest("form") === btn.closest("form"))));
      if (!nearComposer && !/send|submit|run/.test(label)) return;
      const source =
        editable ?? ((btn.closest("form")?.querySelector("textarea, [contenteditable='true'], .ql-editor") as HTMLElement | null) ?? null);
      const text = textOf(source);
      if (text.trim()) {
        armPrompt(text);
        noteTyping(text);
        console.info("[Sentinel] prompt armed via send button (", text.length, "chars)");
      }
    },
    true,
  );

  // Continuous typing tracker (the third capture path): every input event on
  // an editable refreshes `lastTyped`, so a prompt can always be paired with
  // the response it triggered — even if both arming hooks miss.
  document.addEventListener(
    "input",
    (ev) => {
      const editable = editableIn(ev.target as Element | null) as HTMLElement | null;
      if (!editable) return;
      noteTyping(textOf(editable));
    },
    true,
  );
}

function fingerprint(m: CollectedMessage): string {
  // djb2 — fast, local, and no content ever leaves here unencrypted anyway
  // (the backend hashes at ingest for storage).
  let hash = 5381;
  const input = `${m.role}\u0000${m.text}`;
  for (let i = 0; i < input.length; i++) {
    hash = ((hash << 5) + hash + input.charCodeAt(i)) | 0;
  }
  return `${hash >>> 0}:${m.text.length}`;
}

function emit(m: CollectedMessage): void {
  void m; // prompts-only: emit() is only ever called for user prompts
  const event: CaptureEvent = {
    client_event_id: crypto.randomUUID(),
    occurred_at: new Date().toISOString(),
    ai_tool: toolForSite(),
    domain: location.host,
    page_path: location.pathname.slice(0, 512),
    prompt_text: m.text.slice(0, 8000),
  };
  chrome.runtime.sendMessage({ type: "capture", event }).catch(() => {
    /* background unavailable (extension reloading) — drop */
  });
}

function toolForSite() {
  return getAdapter(location.host).tool;
}

/**
 * DLP pre-flight: intercept form submission, ask the backend for a verdict,
 * block/warn before anything is sent.
 *
 * Only form-based submission can be intercepted synchronously enough to be
 * reliable; Enter-key-only composers (no <form> ancestor) fall through and are
 * still fully captured + classified post-hoc — see README "Known limitations".
 */
function installPreflight(adapter: SiteAdapter): void {
  let bypass = false;
  let hookedForm: HTMLFormElement | null = null;

  const hook = () => {
    const composer = adapter.composer();
    if (!composer) return;
    const form = composer.closest("form");
    if (!(form instanceof HTMLFormElement) || form === hookedForm) return;
    hookedForm = form;

    form.addEventListener(
      "submit",
      async (event) => {
        if (bypass) {
          bypass = false;
          return;
        }
        const prompt = adapter.composerText();
        if (!prompt.trim()) return;

        // Decide synchronously: cancel this send, ask the backend, then either
        // show the overlay (block) or re-submit transparently (allowed).
        event.preventDefault();
        event.stopImmediatePropagation();

        let verdict: { action: string; message: string | null };
        try {
          verdict = (await chrome.runtime.sendMessage({
            type: "preflight",
            prompt,
            tool: adapter.tool,
            domain: location.host,
            pagePath: location.pathname,
          })) as { action: string; message: string | null };
        } catch {
          failOpen(form, () => (bypass = false));
          return;
        }

        if (!verdict || verdict.action === "block") {
          if (verdict) {
            showOverlay(
              "block",
              verdict.message || "Blocked by your organization's DLP policy.",
            );
          } else {
            failOpen(form, () => (bypass = false));
          }
          return;
        }
        if (verdict.action === "warn") {
          showOverlay("warn", verdict.message || "This prompt may contain sensitive data.");
        }
        bypass = true;
        form.requestSubmit();
      },
      true,
    );
  };

  hook();
  // SPAs mount composers late — retry briefly until found.
  let attempts = 0;
  const interval = window.setInterval(() => {
    attempts += 1;
    if (hookedForm || attempts > 20) {
      window.clearInterval(interval);
      return;
    }
    hook();
  }, 1000);
}

/** Backend unreachable: send anyway (capture queue retries later). */
function failOpen(form: HTMLFormElement, reset: () => void): void {
  reset();
  form.requestSubmit();
}
