// GENERATED FILE — do not edit by hand.
// Source of truth: backend/schemas.py
// Regenerate with:  python scripts/gen_types.py

export type MissionState =
  | "SEARCHING"
  | "DETECTED"
  | "TRACKING"
  | "THREAT_CONFIRMED"
  | "FOLLOWING"
  | "AWAITING_AUTHORIZATION"
  | "AUTHORIZED"
  | "ACTUATED"
  | "TARGET_LOST"
  | "ERROR";

export type EventKind =
  | "info"
  | "detection"
  | "track"
  | "state"
  | "authorization"
  | "actuation"
  | "warning"
  | "error";

export type InterceptorPhase =
  | "IDLE"
  | "LAUNCH"
  | "FLIGHT"
  | "INTERCEPT"
  | "SPENT";

export type PlatformClass =
  | "UNKNOWN"
  | "MULTIROTOR"
  | "FIXED_WING";

export interface BBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Point {
  x: number;
  y: number;
}

export interface PlatformFeatures {
  straightness: number;
  speed_cv: number;
  turn_rate: number;
  hover_fraction: number;
  mean_speed: number;
  samples: number;
}

export interface SpeedEstimate {
  available: boolean;
  /** Frame widths per second — always present, a direct measurement. */
  image_speed: number;
  range_m: number;
  speed_ms: number;
  speed_kmh: number;
  assumed_size_m: number;
  plausible: boolean;
  detail: string;
}

export interface Velocity {
  x: number;
  y: number;
  speed: number;
}

export interface TrajectoryPoint {
  x: number;
  y: number;
  /** Seconds ahead of the current frame. */
  t: number;
}

export interface Trajectory {
  valid: boolean;
  points: TrajectoryPoint[];
  velocity: Velocity | null;
  residual: number;
  confidence: number;
  horizon: number;
}

export interface InterceptSolution {
  feasible: boolean;
  point: Point | null;
  time_to_intercept: number;
  launch_point: Point | null;
  detail: string;
}

export interface InterceptorState {
  phase: InterceptorPhase;
  active: boolean;
  position: Point | null;
  launch_point: Point | null;
  aim_point: Point | null;
  trail: Point[];
  progress: number;
  time_since_launch: number;
  time_to_intercept: number;
}

export interface VideoInfo {
  name: string;
  path: string;
  size_mb: number;
  duration: number;
  width: number;
  height: number;
  fps: number;
  is_active: boolean;
  uploaded: boolean;
}

export interface SourceStatus {
  video_source: string;
  active_video: string | null;
  camera_index: number;
  detector: string;
  detection_threshold: number;
  detectors_available: string[];
  videos: VideoInfo[];
}

export interface Target {
  target_id: string;
  /** Serialised from `object_class` under the alias `class`. */
  class: string;
  confidence: number;
  bbox: BBox;
  tracking: boolean;
  age_frames: number;
  track_duration: number;
  trail: Point[];
  is_primary: boolean;
  trajectory: Trajectory | null;
  platform: PlatformClass;
  platform_label: string;
  platform_features: PlatformFeatures | null;
  speed: SpeedEstimate | null;
}

export interface ClassCount {
  name: string;
  count: number;
}

export interface DetectionStats {
  detections_last_frame: number;
  detections_total: number;
  frames_processed: number;
  classes: ClassCount[];
  latency_ms: number;
  active_tracks: number;
}

export interface SystemStatus {
  sensor_online: boolean;
  detector: string;
  detector_ready: boolean;
  video_source: string;
  fps: number;
  frame_index: number;
  frame_width: number;
  frame_height: number;
}

export interface MissionStatus {
  state: MissionState;
  target_id: string | null;
  authorization_required: boolean;
  can_authorize: boolean;
  detail: string;
  progress: number;
  state_since: number;
}

export interface MissionEvent {
  timestamp: number;
  kind: EventKind;
  message: string;
}

export interface TelemetryFrame {
  type: "telemetry";
  timestamp: number;
  system: SystemStatus;
  mission: MissionStatus;
  targets: Target[];
  detection: DetectionStats;
  intercept: InterceptSolution | null;
  interceptor: InterceptorState | null;
  events: MissionEvent[];
}

export interface HistoryMessage {
  type: "history";
  events: MissionEvent[];
}

export type ServerMessage = TelemetryFrame | HistoryMessage;

export interface CommandResponse {
  ok: boolean;
  state: MissionState;
  detail: string;
}
