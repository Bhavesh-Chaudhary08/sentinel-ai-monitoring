// Compile-time constants injected by build.mjs via esbuild `define`.
// They are the empty string in local/dev builds, which makes the consumers
// fall back to the localhost defaults.
declare const __PUBLIC_API_URL__: string;
declare const __PUBLIC_DASHBOARD_URL__: string;
