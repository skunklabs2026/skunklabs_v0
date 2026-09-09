/** Display formatting shared across screens. */

import type {
  MissionPhase,
  MissionState,
  PlatformClass,
  ReadinessState,
  SubsystemState,
  TrackStability,
} from "./types";

/** Operator-facing wording for each backend mission state. */
export const STATE_LABEL: Record<MissionState, string> = {
  SEARCHING: "SEARCHING",
  DETECTED: "OBJECT DETECTED",
  TRACKING: "ESTABLISHING TRACK",
  THREAT_CONFIRMED: "THREAT CRITERIA MET",
  FOLLOWING: "FOLLOWING TARGET",
  AWAITING_AUTHORIZATION: "READY FOR AUTHORIZATION",
  // AUTHORIZED is the state in which the launch command crosses the launcher
  // boundary, so the banner names that rather than the operator's click.
  AUTHORIZED: "LAUNCH COMMAND ISSUED",
  ACTUATED: "INTERCEPTOR RELEASE SIMULATED",
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

/** The seven timeline steps, as the operator reads them. */
export const PHASE_LABEL: Record<MissionPhase, string> = {
  SEARCH: "Search",
  DETECT: "Detect",
  TRACK: "Track",
  CONFIRM: "Confirm",
  FOLLOW: "Follow",
  AUTHORIZE: "Authorize",
  LAUNCH: "Launch",
};

export const READINESS_LABEL: Record<ReadinessState, string> = {
  NOT_READY: "NOT READY",
  READY_FOR_AUTHORIZATION: "READY FOR AUTHORIZATION",
  AUTHORIZED: "AUTHORIZED",
  LAUNCH_COMMAND_ISSUED: "LAUNCH COMMAND ISSUED",
};

export const READINESS_COLOR: Record<ReadinessState, string> = {
  NOT_READY: "var(--idle)",
  READY_FOR_AUTHORIZATION: "var(--threat)",
  AUTHORIZED: "var(--armed)",
  LAUNCH_COMMAND_ISSUED: "var(--armed)",
};

/** Readiness condition names, as sentences an operator can act on. */
export const CONDITION_LABEL: Record<string, string> = {
  target_valid: "Target valid",
  track_confirmed: "Track confirmed",
  track_stable: "Track stable",
  canister_operational: "Canister operational",
  launcher_interface_ready: "Launcher interface",
  authorization_valid: "Operator authorization",
};

/**
 * Whether a subsystem state should read as healthy.
 *
 * Only used for the *unknown* states, which are neither good nor bad —
 * everything else comes from the backend's own `nominal` flag, so the UI
 * never second-guesses which state is good for which subsystem.
 */
export const UNKNOWN_SUBSYSTEM_STATES: ReadonlySet<SubsystemState> =
  new Set<SubsystemState>(["N/A", "NOT CONNECTED", "NOT CALIBRATED"]);

export const TRACK_STABILITY_LABEL: Record<TrackStability, string> = {
  UNAVAILABLE: "—",
  UNSTABLE: "UNSTABLE",
  SETTLING: "SETTLING",
  STABLE: "STABLE",
};

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
