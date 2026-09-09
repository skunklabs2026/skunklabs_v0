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

export type MissionPhase =
  | "SEARCH"
  | "DETECT"
  | "TRACK"
  | "CONFIRM"
  | "FOLLOW"
  | "AUTHORIZE"
  | "LAUNCH";

export type PhaseStatus =
  | "PENDING"
  | "ACTIVE"
  | "COMPLETE";

export type EventKind =
  | "info"
  | "detection"
  | "track"
  | "state"
  | "authorization"
  | "actuation"
  | "warning"
  | "error";

export type EventCode =
  | "SYSTEM_START"
  | "SYSTEM_INFO"
  | "SOURCE_CHANGED"
  | "SENSOR_LOST"
  | "SENSOR_RESTORED"
  | "OBJECT_DETECTED"
  | "TRACK_CREATED"
  | "TRACK_CONFIRMED"
  | "TRACK_LOST"
  | "TRACK_REACQUIRED"
  | "THREAT_CRITERIA_MET"
  | "FOLLOWING_TARGET"
  | "ENGAGEMENT_READY"
  | "ENGAGEMENT_NOT_READY"
  | "AUTHORIZATION_REQUESTED"
  | "AUTHORIZATION_REJECTED"
  | "OPERATOR_AUTHORIZED"
  | "LAUNCH_COMMAND_ISSUED"
  | "ACTUATOR_ACKNOWLEDGED"
  | "ACTUATOR_REJECTED"
  | "LAUNCHER_SAFED"
  | "INTERCEPTOR_RELEASE_SIMULATED"
  | "MISSION_RESET"
  | "STATE_CHANGE"
  | "WARNING"
  | "ERROR";

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

export type SubsystemId =
  | "SYSTEM"
  | "SENSOR"
  | "PERCEPTION"
  | "TRACKER"
  | "COMPUTE"
  | "LINK"
  | "LAUNCHER"
  | "INTERCEPTOR"
  | "POWER"
  | "TEMPERATURE";

export type SubsystemState =
  | "OPERATIONAL"
  | "ONLINE"
  | "LOCAL"
  | "SAFE"
  | "ARMED"
  | "STOWED"
  | "INITIALISING"
  | "DEGRADED"
  | "OFFLINE"
  | "FAULT"
  | "N/A"
  | "NOT CONNECTED"
  | "NOT CALIBRATED";

export type ReadinessState =
  | "NOT_READY"
  | "READY_FOR_AUTHORIZATION"
  | "AUTHORIZED"
  | "LAUNCH_COMMAND_ISSUED";

export type LauncherState =
  | "SAFE"
  | "ARMED"
  | "COMMAND_RECEIVED"
  | "ACKNOWLEDGED"
  | "SPENT"
  | "FAULT";

export type TrackStability =
  | "UNAVAILABLE"
  | "UNSTABLE"
  | "SETTLING"
  | "STABLE";

export type TacticalFrame =
  | "SENSOR_FRAME";

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
  /** Operator-facing, sensor-frame view of the extrapolation. */
  projection: TrackProjection | null;
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
  /** Derived on the backend — the UI renders it, it never computes one. */
  phase: MissionPhase;
  phases: PhaseProgress[];
}

export interface PhaseProgress {
  phase: MissionPhase;
  status: PhaseStatus;
  progress: number;
}

export interface MissionEvent {
  timestamp: number;
  kind: EventKind;
  message: string;
  code: EventCode;
  target_id: string | null;
}

export interface Subsystem {
  id: SubsystemId;
  label: string;
  state: SubsystemState;
  detail: string;
  /** True only when a real sensor produced this value. */
  measured: boolean;
  nominal: boolean;
}

export interface CanisterStatus {
  canister_id: string;
  state: SubsystemState;
  detail: string;
  uptime: number;
  subsystems: Subsystem[];
}

export interface ReadinessCondition {
  name: string;
  met: boolean;
  detail: string;
}

export interface EngagementReadiness {
  state: ReadinessState;
  conditions: ReadinessCondition[];
  blocking: string[];
  detail: string;
}

export interface LauncherStatus {
  interface: string;
  state: LauncherState;
  simulated: boolean;
  ready: boolean;
  commands_issued: number;
  last_command_id: string | null;
  last_command_at: number | null;
  last_acknowledged_at: number | null;
  detail: string;
}

/**
 * A sensor-frame extrapolation. NOT a range, a ground track, an impact
 * prediction or a firing solution.
 */
export interface TrackProjection {
  valid: boolean;
  frame: "SENSOR_FRAME";
  direction_deg: number | null;
  direction_label: string;
  stability: TrackStability;
  horizon: number;
  confidence: number;
  points: TrajectoryPoint[];
}

export interface TacticalTrack {
  target_id: string;
  is_primary: boolean;
  /** -1 (left frame edge) .. +1 (right edge); 0 is boresight. */
  bearing_norm: number;
  /** 0 (top of frame) .. 1 (bottom). */
  elevation_norm: number;
  apparent_size: number;
  course_x: number;
  course_y: number;
  speed_norm: number;
  bearing_available: boolean;
  bearing_deg: number | null;
  range_available: boolean;
  range_m: number | null;
  /** Projected path: future bearing (`x`) / elevation (`y`) pairs. */
  path: Point[];
  confidence: number;
  platform: PlatformClass;
  track_duration: number;
  source: string;
}

export interface TacticalPicture {
  frame: TacticalFrame;
  frame_label: string;
  fov_deg: number | null;
  calibrated: boolean;
  /** Confirmed tracks only. */
  tracks: TacticalTrack[];
  /** Detections held but not yet confirmed — counted, not plotted. */
  candidates: number;
  sources: string[];
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
  canister: CanisterStatus;
  readiness: EngagementReadiness;
  launcher: LauncherStatus;
  tactical: TacticalPicture;
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
  readiness: ReadinessState;
}
