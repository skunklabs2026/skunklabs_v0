/**
 * Asking the browser where we are, and telling the backend.
 *
 * Shared by the automatic attempt on load (useDeviceLocation) and the
 * "Use my location" button, because a request made from a click is the one a
 * browser reliably prompts for: an automatic request can be silently refused
 * by a permission policy, and on some systems never shows a prompt at all.
 *
 * Geolocation needs a secure context. http://localhost counts; a bare LAN IP
 * does not, which is the usual reason it never prompts.
 */

import type { ScenarioStore } from "../scenario/store";

export interface DevicePosition {
  latitude: number;
  longitude: number;
}

export function geolocationAvailable(): boolean {
  return typeof navigator !== "undefined" && Boolean(navigator.geolocation);
}

/** Resolves with the device position, or null when it cannot be had. */
export function readDevicePosition(): Promise<DevicePosition | null> {
  if (!geolocationAvailable()) return Promise.resolve(null);
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      ({ coords }) =>
        resolve({ latitude: coords.latitude, longitude: coords.longitude }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 60_000 },
    );
  });
}

/**
 * Ask the browser, then centre the site on the answer. Returns the position so
 * a caller can retry sending it once the backend is reachable again.
 */
export async function requestDeviceLocation(
  store: ScenarioStore,
): Promise<DevicePosition | null> {
  store.setLocation("locating");
  const position = await readDevicePosition();
  if (!position) {
    store.setLocation("unavailable");
    return null;
  }
  store.setLocation("device");
  await store.command("configure", { body: { ...position }, quiet: true });
  return position;
}
