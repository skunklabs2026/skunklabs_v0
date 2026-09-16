/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API and the MJPEG/WebSocket streams are proxied through the dev server
// so the browser sees a single origin. That keeps the frontend free of any
// backend host configuration — it always talks to its own origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      // Without an explicit include, v8 only instruments files that were
      // imported during the run — so untested files vanish from the report
      // instead of showing as 0%, and the thresholds below measure nothing.
      include: ["src/**/*.{ts,tsx}"],
      // types.ts is generated from backend/schemas.py by scripts/gen_types.py.
      // main.tsx is the bootstrap: it calls createRoot on a real document and
      // imports stylesheets, so a test of it would assert that React mounts,
      // not that this app works. Excluded like a __main__ block.
      exclude: [
        "node_modules/",
        "src/test/",
        "src/types.ts",
        "src/main.tsx",
        "src/**/*.d.ts",
      ],
      thresholds: {
        statements: 90,
        branches: 90,
        functions: 90,
        lines: 90,
      },
    },
  },
});
