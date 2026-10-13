import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api (REST + WebSocket) to the FastAPI container, so the
// browser always talks same-origin — no CORS config needed in dev.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
