// Popup: the employee-facing transparency surface.
// Three states: signed out → consent prompt → monitoring active.

import { api, getToken } from "../api/client";
import type { StatusResponse } from "../shared/types";

const $ = <T extends HTMLElement>(sel: string): T => document.querySelector(sel) as T;

const views = {
  loading: $("#view-loading"),
  login: $("#view-login"),
  consent: $("#view-consent"),
  active: $("#view-active"),
};

// Single source of truth for where the dashboard lives. Baked in at build
// time (PUBLIC_DASHBOARD_URL) so a shared build opens YOUR hosted dashboard;
// falls back to the Vite dev server for local builds (use
// http://localhost:3000 when running the compose stack, its FRONTEND_PORT).
const DASHBOARD_URL = __PUBLIC_DASHBOARD_URL__ || "http://localhost:5173";
const REGISTER_URL = `${DASHBOARD_URL}/register`;

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
  const token = await getToken();
  const url = token
    ? `${DASHBOARD_URL}/#ext_token=${encodeURIComponent(token)}`
    : DASHBOARD_URL;
  void chrome.tabs.create({ url });
});

// No sign-up inside the popup — account creation lives on the dashboard.
$("#register-link").addEventListener("click", () => {
  void chrome.tabs.create({ url: REGISTER_URL });
});

$("#logout-btn").addEventListener("click", async () => {
  await send({ type: "logout" });
  await refresh();
});

void refresh();
