// Inline DLP overlay: rendered over the composer when policy says block/warn.
// Uses inline styles only (content scripts can't ship CSS files easily).

const HOST_ID = "aidlp-dlp-overlay";

export function showOverlay(kind: "block" | "warn", message: string): void {
  dismissOverlay();
  const host = document.createElement("div");
  host.id = HOST_ID;
  host.style.cssText =
    "position:fixed;z-index:2147483647;left:50%;top:18%;transform:translateX(-50%);" +
    "width:min(560px,92vw);font-family:system-ui,-apple-system,sans-serif;";

  const isBlock = kind === "block";
  host.innerHTML = `
    <div style="background:${isBlock ? "#7f1d1d" : "#78350f"};color:#fef2f2;
                border:1px solid ${isBlock ? "#ef4444" : "#f59e0b"};border-radius:12px;
                padding:16px 18px;box-shadow:0 18px 40px rgba(0,0,0,.35);">
      <div style="display:flex;align-items:center;gap:8px;font-weight:650;font-size:15px;">
        <span>${isBlock ? "⛔ Prompt blocked" : "⚠️ Sensitive data warning"}</span>
      </div>
      <p style="margin:10px 0 6px;font-size:13.5px;line-height:1.5;">${escapeHtml(message)}</p>
      <p style="margin:4px 0 12px;font-size:11.5px;opacity:.8;">
        ${isBlock
          ? "Your prompt was NOT sent to the AI tool. Edit it and try again — this check ran before anything left your device."
          : "The prompt was sent and has been logged. Remove sensitive details if the task doesn't require them."}
      </p>
      <button id="${HOST_ID}-close" style="background:#fef2f2;color:#111;border:0;border-radius:8px;
              padding:7px 14px;font-weight:600;cursor:pointer;">Dismiss</button>
      <span style="margin-left:10px;font-size:11px;opacity:.75;">Monitored by your organization's AI usage policy</span>
    </div>`;

  document.documentElement.appendChild(host);
  host.querySelector(`#${HOST_ID}-close`)?.addEventListener("click", dismissOverlay);

  // Auto-dismiss warnings; blocks stay until acknowledged.
  if (!isBlock) window.setTimeout(dismissOverlay, 9000);
}

export function dismissOverlay(): void {
  document.getElementById(HOST_ID)?.remove();
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
