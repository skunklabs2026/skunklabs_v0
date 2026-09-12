/** Presentation of scenario values. Formatting only - never mission logic. */

import type {
  EngagementStatus,
  InterceptorStatus,
  MissionState,
  NodeState,
  ScenarioSnapshot,
  TrackStatus,
} from "./contract";
import { missionCounts } from "./select";

/**
 * Status colour families. Green means ready or resolved, red the threat and
 * faults, amber motion in progress, blue what the operator has committed - so
 * colour never contradicts the label next to it.
 */
export type Tone = "neutral" | "info" | "active" | "ready" | "armed" | "alert";

export const MISSION_LABEL: Record<MissionState, string> = {
  IDLE: "Idle",
  RUNNING: "Running",
  COMPLETE: "Complete",
  FAULT: "Fault",
};

export const MISSION_TONE: Record<MissionState, Tone> = {
  IDLE: "neutral",
  RUNNING: "active",
  COMPLETE: "ready",
  FAULT: "alert",
};

export const NODE_LABEL: Record<NodeState, string> = {
  STANDBY: "Standby",
  TRACK_RECEIVED: "Track received",
  ORIENTING: "Orienting",
  READY: "Ready",
  AUTHORIZED: "Authorized",
  SIMULATED_LAUNCH: "Launching",
};

export const NODE_TONE: Record<NodeState, Tone> = {
  STANDBY: "neutral",
  TRACK_RECEIVED: "info",
  ORIENTING: "active",
  READY: "ready",
  AUTHORIZED: "armed",
  SIMULATED_LAUNCH: "armed",
};

export const ENGAGEMENT_LABEL: Record<EngagementStatus, string> = {
  PROPOSED: "Node orienting",
  AWAITING_AUTHORIZATION: "Awaiting decision",
  AUTHORIZED: "Authorized",
  IN_FLIGHT: "In flight",
  INTERCEPTED: "Intercepted · sim",
  DECLINED: "Declined",
  ABORTED: "Aborted",
};

export const ENGAGEMENT_TONE: Record<EngagementStatus, Tone> = {
  PROPOSED: "active",
  AWAITING_AUTHORIZATION: "ready",
  AUTHORIZED: "armed",
  IN_FLIGHT: "armed",
  INTERCEPTED: "ready",
  DECLINED: "neutral",
  ABORTED: "alert",
};

export const TRACK_LABEL: Record<TrackStatus, string> = {
  INBOUND: "Inbound",
  INTERCEPTED: "Intercepted · sim",
  REACHED_SITE: "Reached site",
};

export const TRACK_TONE: Record<TrackStatus, Tone> = {
  INBOUND: "alert",
  INTERCEPTED: "ready",
  REACHED_SITE: "alert",
};

export const INTERCEPTOR_LABEL: Record<InterceptorStatus, string> = {
  PENDING: "Queued",
  IN_FLIGHT: "In flight",
  INTERCEPT: "Intercept · sim",
  STOOD_DOWN: "Stood down",
};

export const INTERCEPTOR_TONE: Record<InterceptorStatus, Tone> = {
  PENDING: "neutral",
  IN_FLIGHT: "armed",
  INTERCEPT: "ready",
  STOOD_DOWN: "neutral",
};

/** Compass angle, zero-padded: 72.3 → "072.3°". */
export function formatHeading(deg: number, digits = 1): string {
  // Round before wrapping, so 359.96 reads "000.0°" rather than "360.0°".
  const rounded = Number(deg.toFixed(digits));
  const wrapped = ((rounded % 360) + 360) % 360;
  const [whole, fraction] = wrapped.toFixed(digits).split(".");
  return `${whole.padStart(3, "0")}${fraction ? `.${fraction}` : ""}°`;
}

/** Elevation angle: 12 → "12.0°". */
export function formatElevation(deg: number, digits = 1): string {
  return `${deg.toFixed(digits)}°`;
}

export function formatKm(km: number): string {
  return `${km.toFixed(1)} km`;
}

/** Local wall-clock time of an epoch-seconds timestamp: "14:32:11". */
export function formatClock(epochSeconds: number): string {
  const date = new Date(epochSeconds * 1000);
  return [date.getHours(), date.getMinutes(), date.getSeconds()]
    .map((part) => String(part).padStart(2, "0"))
    .join(":");
}

/** Seconds since start: 72.4 → "T+01:12". */
export function formatElapsed(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  const minutes = String(Math.floor(whole / 60)).padStart(2, "0");
  return `T+${minutes}:${String(whole % 60).padStart(2, "0")}`;
}

/** "1 interceptor", "2 interceptors". */
export function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

/** One line saying what is happening now and what, if anything, to do next. */
export function describeSituation(snapshot: ScenarioSnapshot): string {
  const counts = missionCounts(snapshot);
  switch (snapshot.state) {
    case "IDLE": {
      const scenario = snapshot.scenarios.find(
        (s) => s.id === snapshot.scenario_id,
      );
      return scenario
        ? `${scenario.name} - ${scenario.description}. Start the demo when ready.`
        : "Select a threat scenario and start the demo.";
    }
    case "RUNNING":
      if (counts.pending > 0) {
        return `${plural(counts.pending, "response")} awaiting operator decision`;
      }
      if (counts.inFlight > 0) {
        return `${plural(counts.inFlight, "simulated interceptor")} in flight`;
      }
      if (counts.inside === 0) {
        return `${plural(counts.inbound, "threat")} inbound, outside the protected area`;
      }
      return `${plural(counts.inside, "threat")} inside the protected area`;
    case "COMPLETE":
      return `Mission complete - ${counts.intercepted} of ${plural(counts.threats, "threat")} intercepted (simulated)`;
    case "FAULT":
      return snapshot.fault ? `Fault - ${snapshot.fault}` : "Fault";
  }
}
