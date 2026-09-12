/**
 * Where the backend lives.
 *
 * Same-origin by default, which is what both supported deployments give us:
 * in development Vite proxies /api and /ws to the backend, and in production
 * the backend serves the built frontend itself. `VITE_API_BASE` is the escape
 * hatch for the third case - UI and API on different hosts - so that setup
 * needs an env var rather than a code change.
 */

const RAW_BASE = import.meta.env.VITE_API_BASE ?? "";

/** Base URL with any trailing slash removed, so joining is unambiguous. */
export const API_BASE = RAW_BASE.replace(/\/+$/, "");

/** Absolute URL for an HTTP endpoint. */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

/**
 * Absolute URL for the telemetry WebSocket.
 *
 * The protocol has to track the page's: a wss: page cannot open a ws: socket,
 * and browsers reject the mixed connection outright.
 */
export function wsUrl(path: string): string {
  if (API_BASE) {
    return `${API_BASE.replace(/^http/, "ws")}${path}`;
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${path}`;
}
