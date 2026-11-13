// Options page: API base, live known-domain list, local domain overrides.

import { api, getApiBase, setApiBase } from "../api/client";

const $ = <T extends HTMLElement>(sel: string): T => document.querySelector(sel) as T;

async function loadDomains(): Promise<void> {
  const list = $("#domain-list");
  try {
    const resp = await api.aiDomains();
    list.innerHTML = "";
    for (const domain of resp.domains) {
      const li = document.createElement("li");
      li.textContent = domain;
      list.appendChild(li);
    }
    if (!resp.domains.length) {
      list.innerHTML = '<li class="hint">No domains configured on the backend.</li>';
    }
  } catch (err) {
    list.innerHTML = `<li class="hint">Could not fetch (${(err as Error).message}) — showing none.</li>`;
  }
}

// Broad https access is optional: the manifest grants host permissions for the
// known AI platforms only, so coverage of brand-new AI sites is an explicit
// opt-in the user grants here (store review expects exactly this split).
const BROAD_ORIGINS = ["https://*/*"];

async function syncBroadState(): Promise<void> {
  const btn = $<HTMLButtonElement>("#toggle-broad");
  const status = $("#broad-status");
  const granted = await chrome.permissions.contains({ origins: BROAD_ORIGINS });
  btn.textContent = granted ? "Disable extended detection" : "Enable extended detection";
  status.textContent = granted
    ? "On — other https sites are checked for AI chat interfaces; a page is only reported when one is detected."
    : "Off — only the known AI platforms listed above are scanned.";
}

async function init(): Promise<void> {
  $<HTMLInputElement>("#api-base").value = await getApiBase();
  await syncBroadState();

  const stored = await chrome.storage.local.get("extra_domains");
  const extra = (stored.extra_domains as string[] | undefined) ?? [];
  $<HTMLInputElement>("#extra-domains").value = extra.join(", ");

  await loadDomains();
}

$("#save-api").addEventListener("click", async () => {
  const base = $<HTMLInputElement>("#api-base").value.trim();
  if (!base) return;
  await setApiBase(base);
  await chrome.runtime.sendMessage({ type: "setApiBase", base });
  flash("API base saved.");
  await loadDomains();
});

$("#save-domains").addEventListener("click", async () => {
  const domains = $<HTMLInputElement>("#extra-domains")
    .value.split(",")
    .map((d) => d.trim().toLowerCase())
    .filter((d) => /^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$/.test(d));
  await chrome.storage.local.set({ extra_domains: domains });
  await chrome.runtime.sendMessage({ type: "resync" });
  flash(`Saved ${domains.length} local domain(s); content scripts re-synced.`);
});

$("#toggle-broad").addEventListener("click", async () => {
  const granted = await chrome.permissions.contains({ origins: BROAD_ORIGINS });
  if (granted) {
    await chrome.permissions.remove({ origins: BROAD_ORIGINS });
  } else {
    // Must run inside the click gesture for Chrome to show the prompt.
    await chrome.permissions.request({ origins: BROAD_ORIGINS });
  }
  await syncBroadState();
  await chrome.runtime.sendMessage({ type: "resync" });
});

function flash(message: string): void {
  const el = $("#save-msg");
  el.textContent = message;
  window.setTimeout(() => {
    el.textContent = "";
  }, 4000);
}

void init();
