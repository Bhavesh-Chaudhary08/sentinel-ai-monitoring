// Minimal, dependency-light bundler for the MV3 extension.
// esbuild bundles each entry into dist/ (IIFE — works as a classic service
// worker and content script without module wiring), then static assets are
// copied over. Run: npm run build  (or npm run dev for --watch).
import { build, context } from "esbuild";
import { copyFile, mkdir } from "node:fs/promises";
import { watch } from "node:fs";

const watchMode = process.argv.includes("--watch");

// Public URLs baked in at build time so a build shared with friends "just
// works" on their machines with zero config. Pass them when you build for
// sharing:
//   PUBLIC_API_URL=https://your.domain/api/v1 npm run build
//   PUBLIC_DASHBOARD_URL=https://your.domain npm run build
// Omitted → localhost (local dev / docker-compose on this machine).
const PUBLIC_API_URL = process.env.PUBLIC_API_URL || "";
const PUBLIC_DASHBOARD_URL = process.env.PUBLIC_DASHBOARD_URL || "";

const entries = [
  { entryPoints: ["src/background/service_worker.ts"], outfile: "dist/background.js" },
  { entryPoints: ["src/content/index.ts"], outfile: "dist/content.js" },
  { entryPoints: ["src/popup/popup.ts"], outfile: "dist/popup.js" },
  { entryPoints: ["src/options/options.ts"], outfile: "dist/options.js" },
];

const common = {
  bundle: true,
  format: "iife",
  target: "chrome114",
  logLevel: "info",
  sourcemap: false,
  minify: false, // readable output helps during demo/debug
  // Inject the public URLs as compile-time constants; the source reads them
  // via the __PUBLIC_API_URL__ / __PUBLIC_DASHBOARD_URL__ globals and falls
  // back to localhost when they're empty (dev builds).
  define: {
    __PUBLIC_API_URL__: JSON.stringify(PUBLIC_API_URL),
    __PUBLIC_DASHBOARD_URL__: JSON.stringify(PUBLIC_DASHBOARD_URL),
  },
};

const staticAssets = [
  ["manifest.json", "dist/manifest.json"],
  ["popup/popup.html", "dist/popup.html"],
  ["popup/popup.css", "dist/popup.css"],
  ["options/options.html", "dist/options.html"],
  ["options/options.css", "dist/options.css"],
];

await mkdir("dist", { recursive: true });

for (const [from, to] of staticAssets) {
  await copyFile(from, to);
}

if (watchMode) {
  for (const entry of entries) {
    const ctx = await context({ ...common, ...entry });
    await ctx.watch();
  }
  for (const [from, to] of staticAssets) {
    watch(from, () => copyFile(from, to).catch(console.error));
  }
  console.log("esbuild watching…");
} else {
  for (const entry of entries) {
    await build({ ...common, ...entry });
  }
  console.log("extension built → extension/dist (load unpacked in chrome://extensions)");
}
