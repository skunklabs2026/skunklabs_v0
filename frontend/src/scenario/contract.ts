// GENERATED FILE - do not edit by hand.
// Source of truth: backend/scenario/models.py
// Regenerate with:  python scripts/gen_types.py

export type MissionState = "IDLE" | "RUNNING" | "COMPLETE" | "FAULT";

export type NodeState =
  | "STANDBY"
  | "TRACK_RECEIVED"
  | "ORIENTING"
  | "READY"
  | "AUTHORIZED"
  | "SIMULATED_LAUNCH";

export type TrackStatus = "INBOUND" | "INTERCEPTED" | "REACHED_SITE";

export type EngagementStatus =
  | "PROPOSED"
  | "AWAITING_AUTHORIZATION"
  | "AUTHORIZED"
  | "IN_FLIGHT"
  | "INTERCEPTED"
  | "DECLINED"
  | "ABORTED";

export type InterceptorStatus =
  "PENDING" | "IN_FLIGHT" | "INTERCEPT" | "STOOD_DOWN";

export type LocationSource = "DEVICE" | "DEFAULT";

export interface GeoPoint {
  latitude: number;
  longitude: number;
}

export interface ScenarioOption {
  id: string;
  name: string;
  description: string;
  threat_count: number;
}

export interface ProtectedSite {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  protected_radius_km: number;
  location_source: LocationSource;
}

export interface DefenseNode {
  id: string;
  latitude: number;
  longitude: number;
  coverage_radius_km: number;
  current_yaw_deg: number;
  target_yaw_deg: number;
  current_pitch_deg: number;
  target_pitch_deg: number;
  state: NodeState;
  engagement_id: string | null;
  inventory: number;
  inventory_capacity: number;
}

export interface Track {
  id: string;
  latitude: number;
  longitude: number;
  altitude_m: number;
  heading_deg: number;
  speed_kmh: number;
  status: TrackStatus;
  source: string;
  site_distance_km: number;
  inside_protected_area: boolean;
  engagement_id: string | null;
  trail: GeoPoint[];
}

export interface Engagement {
  id: string;
  node_id: string;
  track_id: string;
  status: EngagementStatus;
  proposed_interceptors: number;
  range_km: number;
  bearing_deg: number;
  elevation_deg: number;
  interceptor_ids: string[];
  intercept_point: GeoPoint | null;
}

export interface SimulatedInterceptor {
  id: string;
  node_id: string;
  track_id: string;
  engagement_id: string;
  latitude: number;
  longitude: number;
  heading_deg: number;
  state: InterceptorStatus;
  trail: GeoPoint[];
}

export interface ScenarioEvent {
  timestamp: number;
  message: string;
}

export interface ScenarioSnapshot {
  type: "scenario";
  revision: number;
  state: MissionState;
  scenario_id: string;
  scenarios: ScenarioOption[];
  running: boolean;
  elapsed_s: number;
  time_scale: number;
  site: ProtectedSite;
  nodes: DefenseNode[];
  tracks: Track[];
  engagements: Engagement[];
  interceptors: SimulatedInterceptor[];
  decision_queue: string[];
  can_start: boolean;
  can_configure: boolean;
  fault: string | null;
  events: ScenarioEvent[];
}

export interface ScenarioCommandResult {
  ok: boolean;
  detail: string;
  snapshot: ScenarioSnapshot;
}
