/** Display formatting shared across screens. */

import type { MissionState, PlatformClass } from "./types";

/** Operator-facing wording for each backend mission state. */
export const STATE_LABEL: Record<MissionState, string> = {
  SEARCHING: "SEARCHING",
  DETECTED: "TARGET DETECTED",
  TRACKING: "TRACKING",
  THREAT_CONFIRMED: "THREAT CONFIRMED",
  FOLLOWING: "TARGET LOCKED / FOLLOWING",
  AWAITING_AUTHORIZATION: "AUTHORIZATION REQUIRED",
  AUTHORIZED: "ENGAGEMENT AUTHORIZED",
  ACTUATED: "INTERCEPTOR LAUNCH SIMULATED",
  TARGET_LOST: "TARGET LOST",
  ERROR: "SYSTEM ERROR",
};

export const STATE_COLOR: Record<MissionState, string> = {
  SEARCHING: "var(--idle)",
  DETECTED: "var(--track)",
  TRACKING: "var(--track)",
  THREAT_CONFIRMED: "var(--threat)",
  FOLLOWING: "var(--threat)",
  AWAITING_AUTHORIZATION: "var(--threat)",
  AUTHORIZED: "var(--armed)",
  ACTUATED: "var(--armed)",
  TARGET_LOST: "var(--idle)",
  ERROR: "var(--threat)",
};

/** States that should draw the operator's eye. */
export const URGENT_STATES: ReadonlySet<MissionState> = new Set<MissionState>([
  "AWAITING_AUTHORIZATION",
]);

/** Short airframe labels for the console. */
export const PLATFORM_LABEL: Record<PlatformClass, string> = {
  UNKNOWN: "UNCLASSIFIED",
  MULTIROTOR: "FPV / MULTIROTOR",
  FIXED_WING: "FIXED-WING",
};

export function formatDuration(seconds: number): string {
  if (!seconds) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return m > 0 ? `${m}m ${String(s).padStart(2, "0")}s` : `${s}s`;
}

export function formatClock(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleTimeString("en-GB", {
    hour12: false,
  });
}

/** Trim a path to its filename. */
export function basename(path: string | null | undefined): string | null {
  if (!path) return null;
  return path.split("/").pop() ?? path;
}
