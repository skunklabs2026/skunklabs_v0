/**
 * The two operational views, plus the legacy sensor lab, addressed by path:
 *
 *   /map         defense and situational awareness
 *   /launcher    the local node - what NODE-01 is doing, what is authorized
 *   /sensor-lab  the original video console (deliberately unlinked)
 *
 * History API rather than a router dependency: three routes do not justify
 * one. The backend answers these paths with index.html (see backend/main.py);
 * the Vite dev server does the same by default.
 */

import { useEffect, useSyncExternalStore } from "react";

export type Route = "map" | "launcher" | "sensor-lab";

export const ROUTE_PATH: Record<Route, string> = {
  map: "/map",
  launcher: "/launcher",
  "sensor-lab": "/sensor-lab",
};

export function parseRoute(pathname: string): Route {
  const path = pathname.replace(/\/+$/, "");
  if (path === ROUTE_PATH.launcher) return "launcher";
  if (path === ROUTE_PATH["sensor-lab"]) return "sensor-lab";
  return "map";
}

const listeners = new Set<() => void>();

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  window.addEventListener("popstate", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("popstate", onChange);
  };
}

/** Change view without reloading - the mission keeps running underneath. */
export function navigate(route: Route, { replace = false } = {}): void {
  const path = ROUTE_PATH[route];
  if (window.location.pathname === path) return;
  if (replace) window.history.replaceState(null, "", path);
  else window.history.pushState(null, "", path);
  listeners.forEach((listener) => listener());
}

export function useRoute(): Route {
  const pathname = useSyncExternalStore(subscribe, () => window.location.pathname);
  const route = parseRoute(pathname);

  // "/" and unknown paths settle on their canonical URL.
  useEffect(() => {
    if (pathname !== ROUTE_PATH[route]) navigate(route, { replace: true });
  }, [pathname, route]);

  return route;
}
