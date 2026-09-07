/** Mission commands: the two things an operator can tell the backend to do. */

import type { CommandResponse, MissionEvent, TelemetryFrame } from "../types";
import { get, post } from "./client";
import { endpoints } from "./endpoints";

export function authorize(): Promise<CommandResponse> {
  return post<CommandResponse>(endpoints.authorize());
}

export function reset(): Promise<CommandResponse> {
  return post<CommandResponse>(endpoints.reset());
}

/** Snapshot fallback. Live use goes through the telemetry socket. */
export function fetchTelemetry(): Promise<TelemetryFrame | null> {
  return get<TelemetryFrame | null>(endpoints.telemetry());
}

export function fetchEvents(): Promise<MissionEvent[]> {
  return get<MissionEvent[]>(endpoints.events());
}
