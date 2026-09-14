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
      exclude: ["node_modules/", "src/test/", "src/types.ts", "src/**/*.d.ts"],
      thresholds: {
        // The api/ layer is the contract with the backend — CLAUDE.md's rule
        // that the UI never calls fetch directly is only worth anything if
        // this layer is actually covered. Held at 90.
        "src/api/**": {
          statements: 90,
          branches: 90,
          functions: 90,
          lines: 90,
        },
        // Everything else is a floor set from the measured figure, not an
        // aspiration: the React component and hook layers are largely
        // untested. This is a ratchet — raise it as tests land. It was
        // previously 90 across the board, which passed only because no file
        // was instrumented at all.
        statements: 20,
        branches: 12,
        functions: 28,
        lines: 21,
      },
    },
  },
});
