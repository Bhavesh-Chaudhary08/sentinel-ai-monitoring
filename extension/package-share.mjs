// One-command "share build": bakes YOUR hosted URL into the extension and
// zips dist/ so friends can install it with zero configuration.
//
//   node package-share.mjs https://your-app.onrender.com
//
// → builds dist/ with PUBLIC_API_URL/PUBLIC_DASHBOARD_URL baked in
// → writes sentinel-extension-<host>.zip next to dist/
//
// Friends then: unzip → chrome://extensions → Developer mode → Load unpacked.
// The extension already points at your hosted site; no settings to change.
import { execFileSync } from "node:child_process";
import { rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const url = process.argv[2];
if (!url) {
  console.error("usage: node package-share.mjs https://your-hosted-site.example");
  process.exit(1);
}
const normalized = url.replace(/\/+$/, "");
if (!/^https?:\/\/.+/.test(normalized)) {
  console.error(`not an http(s) url: ${url}`);
  process.exit(1);
}

const here = path.dirname(fileURLToPath(import.meta.url));
const host = new URL(normalized).host.replace(/[^a-z0-9.-]/gi, "-");
const zipName = `sentinel-extension-${host}.zip`;

console.log(`building extension pointed at ${normalized} …`);
execFileSync(process.execPath, [path.join(here, "build.mjs")], {
  cwd: here,
  stdio: "inherit",
  env: {
    ...process.env,
    PUBLIC_API_URL: `${normalized}/api/v1`,
    PUBLIC_DASHBOARD_URL: normalized,
  },
});

const zipPath = path.join(here, zipName);
await rm(zipPath, { force: true });
const distDir = path.join(here, "dist");
if (process.platform === "win32") {
  // PowerShell's Compress-Archive is always present; Git Bash's GNU tar
  // has no `-a` flag (that's bsdtar-only), so don't rely on `tar` here.
  execFileSync(
    "powershell",
    [
      "-NoProfile",
      "-Command",
      `Compress-Archive -Path '${distDir}\\*' -DestinationPath '${zipPath}' -Force`,
    ],
    { stdio: "inherit" },
  );
} else {
  // bsdtar (macOS) picks zip from the filename extension; Linux falls back
  // to `zip` since GNU tar lacks `-a`.
  try {
    execFileSync("tar", ["-a", "-cf", zipPath, "-C", distDir, "."], { stdio: "inherit" });
  } catch {
    execFileSync("sh", ["-c", `cd '${distDir}' && zip -qr '${zipPath}' .`], {
      stdio: "inherit",
    });
  }
}

console.log(`\n✓ ${path.join("..", zipName)}`);
console.log("  send this zip to friends → unzip → chrome://extensions →");
console.log("  Developer mode → Load unpacked → select the unzipped folder.");
