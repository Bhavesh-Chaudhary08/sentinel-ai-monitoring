// Per-site adapters. UI selectors drift as products ship redesigns — that's
// inherent to extension capture; keep selectors tolerant (multiple fallbacks)
// and prefer semantic hooks (data-*) over styling classes.

import type { AiTool } from "../shared/types";

export interface CollectedMessage {
  role: "user" | "assistant";
  text: string;
}

export interface SiteAdapter {
  tool: AiTool;
  /** Composer element used for DLP pre-flight interception. */
  composer(): HTMLElement | null;
  /** Current prompt text inside the composer. */
  composerText(): string;
  /** All conversation messages currently rendered in the DOM. */
  collect(): CollectedMessage[];
}

function textOf(el: Element | null): string {
  if (!el) return "";
  return ((el as HTMLElement).innerText || el.textContent || "").trim();
}

/**
 * querySelectorAll that also pierces OPEN shadow roots — chat UIs increasingly
 * encapsulate message lists in Web Components, where plain selectors never match.
 */
function deepQueryAll(root: ParentNode, selector: string): Element[] {
  const out: Element[] = [];
  const visit = (node: ParentNode): void => {
    try {
      out.push(...Array.from(node.querySelectorAll(selector)));
    } catch {
      /* invalid selector on this node — skip */
    }
    const walker = (node as Document | Element).querySelectorAll?.("*") ?? [];
    for (const el of Array.from(walker)) {
      if (el.shadowRoot) visit(el.shadowRoot);
    }
  };
  visit(root);
  return out;
}

function msg(role: "user" | "assistant", el: Element): CollectedMessage {
  return { role, text: textOf(el) };
}

function visibleLargestTextarea(): HTMLTextAreaElement | null {
  const areas = Array.from(document.querySelectorAll<HTMLTextAreaElement>("textarea"));
  const visible = areas.filter((t) => t.offsetParent !== null && !t.disabled);
  if (!visible.length) return null;
  return visible.sort((a, b) => b.value.length - a.value.length)[0];
}

const chatgpt: SiteAdapter = {
  tool: "chatgpt",
  composer: () =>
    deepQueryAll(document, "#prompt-textarea")[0] as HTMLElement ??
    document.querySelector<HTMLElement>("form textarea") ??
    visibleLargestTextarea(),
  composerText: () => {
    const ed = deepQueryAll(document, "#prompt-textarea")[0] as HTMLElement | undefined;
    if (ed) return textOf(ed);
    return document.querySelector<HTMLTextAreaElement>("form textarea")?.value ?? "";
  },
  collect: () => {
    // Primary: ChatGPT's role attributes (deep-queried for shadow DOM).
    // Fallbacks: the assistant markdown container + test ids, in case the
    // attribute moved or was renamed in a redesign. Identical text dedupes.
    const users = deepQueryAll(document, '[data-message-author-role="user"]');
    const assistants = deepQueryAll(
      document,
      '[data-message-author-role="assistant"], [data-testid^="conversation-turn"] .markdown, .agent-turn .markdown, .markdown.prose',
    );
    return [
      ...users.map((el) => msg("user", el)),
      ...assistants.map((el) => msg("assistant", el)),
    ];
  },
};

const gemini: SiteAdapter = {
  tool: "gemini",
  composer: () =>
    document.querySelector<HTMLElement>("rich-textarea .ql-editor") ??
    document.querySelector<HTMLElement>("rich-textarea textarea") ??
    visibleLargestTextarea(),
  composerText: () =>
    textOf(document.querySelector("rich-textarea .ql-editor")) ||
    (document.querySelector<HTMLTextAreaElement>("rich-textarea textarea")?.value ?? ""),
  collect: () => [
    ...Array.from(document.querySelectorAll("user-query")).map((el) => msg("user", el)),
    ...Array.from(document.querySelectorAll("model-response")).map((el) => msg("assistant", el)),
  ],
};

const claude: SiteAdapter = {
  tool: "claude",
  composer: () =>
    document.querySelector<HTMLElement>("fieldset [contenteditable='true']") ??
    document.querySelector<HTMLElement>(".ProseMirror") ??
    visibleLargestTextarea(),
  composerText: () =>
    textOf(
      document.querySelector("fieldset [contenteditable='true']") ??
        document.querySelector(".ProseMirror"),
    ) || (document.querySelector<HTMLTextAreaElement>("textarea")?.value ?? ""),
  collect: () => [
    ...Array.from(
      document.querySelectorAll("[data-testid='user-message'], .font-user-message"),
    ).map((el) => msg("user", el)),
    ...Array.from(
      document.querySelectorAll("[data-testid='assistant-message'], .font-claude-message"),
    ).map((el) => msg("assistant", el)),
  ],
};

const copilot: SiteAdapter = {
  tool: "copilot",
  composer: () =>
    document.querySelector<HTMLElement>("#userInput") ?? visibleLargestTextarea(),
  composerText: () =>
    (document.querySelector<HTMLTextAreaElement>("#userInput")?.value ?? "") ||
    textOf(document.querySelector("#userInput")),
  collect: () => {
    const out: CollectedMessage[] = [];
    for (const el of document.querySelectorAll(".cib-message, [class*='message']")) {
      const cls = (el.className || "").toString().toLowerCase();
      const text = textOf(el);
      if (!text || text.length > 30_000) continue;
      if (/user|you/.test(cls)) out.push(msg("user", el));
      else if (/bot|assistant|ai/.test(cls)) out.push(msg("assistant", el));
    }
    return out;
  },
};

/** Conservative fallback for dynamically-registered shadow-AI domains. */
const generic: SiteAdapter = {
  tool: "other",
  composer: () =>
    document.querySelector<HTMLElement>(
      "textarea[placeholder*='message' i], textarea[placeholder*='chat' i], textarea[placeholder*='ask' i], [contenteditable='true'][aria-label*='message' i]",
    ) ?? visibleLargestTextarea(),
  composerText: () => {
    const el =
      document.querySelector<HTMLTextAreaElement>(
        "textarea[placeholder*='message' i], textarea[placeholder*='chat' i]",
      ) ?? visibleLargestTextarea();
    return el ? el.value : textOf(document.querySelector("[contenteditable='true']"));
  },
  collect: () => {
    const out: CollectedMessage[] = [];
    const candidates = document.querySelectorAll(
      "[data-testid*='message' i], [class*='message-bubble'], [class*='user-message'], [class*='assistant-message'], [class*='chat-message']",
    );
    for (const el of candidates) {
      const cls = (el.className || "").toString().toLowerCase();
      const testid = (el.getAttribute("data-testid") || "").toLowerCase();
      const text = textOf(el);
      if (!text || text.length > 30_000) continue;
      const hint = `${cls} ${testid}`;
      if (/user|you|human|query|prompt/.test(hint)) out.push(msg("user", el));
      else if (/assistant|bot|ai|model|response/.test(hint)) out.push(msg("assistant", el));
    }
    return out;
  },
};

const HOST_MAP: Array<{ match: RegExp; adapter: SiteAdapter }> = [
  { match: /(chatgpt\.com|chat\.openai\.com|openai\.com)/, adapter: chatgpt },
  { match: /(gemini\.google\.com|aistudio\.google\.com)/, adapter: gemini },
  { match: /(claude\.ai|anthropic\.com)/, adapter: claude },
  { match: /(copilot\.microsoft\.com|github\.com)/, adapter: copilot },
];

export function getAdapter(host: string): SiteAdapter {
  const hit = HOST_MAP.find((entry) => entry.match.test(host));
  return hit ? hit.adapter : generic;
}
