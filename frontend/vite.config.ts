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
});
