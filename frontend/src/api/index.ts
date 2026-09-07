/**
 * The backend API, as seen by the UI.
 *
 * Components and hooks import from here and never call `fetch` directly, so
 * URLs, error shapes and retry behaviour have exactly one definition.
 *
 *   config.ts     where the backend is
 *   endpoints.ts  every path
 *   client.ts     the transport and ApiError
 *   mission.ts    authorize / reset / telemetry
 *   source.ts     library, camera, detector, uploads
 */

export { ApiError, isOffline } from "./client";
export { API_BASE } from "./config";
export { endpoints } from "./endpoints";
export * as missionApi from "./mission";
export * as sourceApi from "./source";
