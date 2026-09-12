/**
 * Every backend path, in one place.
 *
 * The point is that a route rename on the backend produces one failing file
 * here rather than a silent 404 discovered during a demo.
 */

import { apiUrl, wsUrl } from "./config";

export type ScenarioCommandName =
  "configure" | "start" | "authorize" | "decline" | "reassign" | "reset";

/** Commands that act on one proposed response rather than the mission. */
const RESPONSE_COMMANDS: ReadonlySet<ScenarioCommandName> = new Set([
  "authorize",
  "decline",
  "reassign",
]);

export const endpoints = {
  // ---- V0 defense scenario ----
  scenario: () => apiUrl("/api/scenario"),
  scenarioCommand: (command: ScenarioCommandName, responseId?: string) =>
    RESPONSE_COMMANDS.has(command)
      ? apiUrl(
          `/api/scenario/responses/${encodeURIComponent(responseId ?? "")}/${command}`,
        )
      : apiUrl(`/api/scenario/${command}`),
  scenarioSocket: () => wsUrl("/ws/scenario"),

  // ---- system + video sensor lab ----
  health: () => apiUrl("/api/health"),
  telemetry: () => apiUrl("/api/telemetry"),
  events: () => apiUrl("/api/events"),

  authorize: () => apiUrl("/api/authorize"),
  reset: () => apiUrl("/api/reset"),

  source: () => apiUrl("/api/source"),
  selectVideo: () => apiUrl("/api/source/video"),
  selectCamera: () => apiUrl("/api/source/camera"),
  selectDetector: () => apiUrl("/api/source/detector"),
  setThreshold: () => apiUrl("/api/source/threshold"),
  upload: () => apiUrl("/api/source/upload"),
  deleteUpload: (name: string) =>
    apiUrl(`/api/source/upload/${encodeURIComponent(name)}`),

  /** MJPEG preview. Used as an <img> src, not fetched. */
  videoStream: () => apiUrl("/api/video"),

  telemetrySocket: () => wsUrl("/ws/telemetry"),
} as const;
