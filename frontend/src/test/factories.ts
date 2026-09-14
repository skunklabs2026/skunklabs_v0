/**
 * Telemetry fixtures.
 *
 * Every builder returns a complete, valid object and takes an overrides
 * object, so a test names only the fields it is actually about. Keeping them
 * here means a schema change (types.ts is generated from backend/schemas.py)
 * breaks one file rather than every component test.
 */

import type {
  BBox,
  EventKind,
  DetectionStats,
  InterceptorState,
  InterceptSolution,
  MissionEvent,
  MissionState,
  MissionStatus,
  Point,
  SourceStatus,
  SpeedEstimate,
  SystemStatus,
  Target,
  TelemetryFrame,
  Trajectory,
  VideoInfo,
} from "../types";

export function makeBBox(o: Partial<BBox> = {}): BBox {
  return { x: 0.4, y: 0.4, width: 0.1, height: 0.1, ...o };
}

export function makeTrajectory(o: Partial<Trajectory> = {}): Trajectory {
  return {
    valid: true,
    points: [
      { x: 0.5, y: 0.5, t: 0.5 },
      { x: 0.6, y: 0.5, t: 1.0 },
    ],
    velocity: { x: 0.2, y: 0, speed: 0.2 },
    residual: 0.001,
    confidence: 0.85,
    horizon: 2,
    ...o,
  };
}

export function makeSpeed(o: Partial<SpeedEstimate> = {}): SpeedEstimate {
  return {
    available: true,
    image_speed: 0.3,
    range_m: 108.3,
    speed_ms: 34,
    speed_kmh: 122.4,
    assumed_size_m: 2.5,
    plausible: true,
    detail: "Assumes Fixed-wing ≈ 2.50 m across at 60° HFOV.",
    ...o,
  };
}

export function makeTarget(o: Partial<Target> = {}): Target {
  return {
    target_id: "UAV-001",
    class: "uav",
    confidence: 0.85,
    bbox: makeBBox(),
    tracking: true,
    age_frames: 0,
    track_duration: 3.2,
    trail: [
      { x: 0.3, y: 0.4 },
      { x: 0.4, y: 0.42 },
    ],
    is_primary: true,
    trajectory: makeTrajectory(),
    platform: "FIXED_WING",
    platform_label: "Fixed-wing",
    platform_features: {
      straightness: 0.95,
      speed_cv: 0.1,
      turn_rate: 0.02,
      hover_fraction: 0,
      mean_speed: 0.3,
      samples: 24,
    },
    speed: makeSpeed(),
    ...o,
  };
}

export function makeSystem(o: Partial<SystemStatus> = {}): SystemStatus {
  return {
    sensor_online: true,
    detector: "motion",
    detector_ready: true,
    video_source: "file:demo_drone.mp4",
    fps: 25,
    frame_index: 120,
    frame_width: 960,
    frame_height: 540,
    ...o,
  };
}

export function makeMission(o: Partial<MissionStatus> = {}): MissionStatus {
  return {
    state: "TRACKING",
    target_id: "UAV-001",
    authorization_required: false,
    can_authorize: false,
    detail: "Track acquired on UAV-001.",
    progress: 0.5,
    state_since: 1_700_000_000,
    ...o,
  };
}

export function makeDetection(o: Partial<DetectionStats> = {}): DetectionStats {
  return {
    detections_last_frame: 1,
    detections_total: 459,
    frames_processed: 600,
    classes: [{ name: "uav", count: 459 }],
    latency_ms: 4.2,
    active_tracks: 1,
    ...o,
  };
}

export function makeIntercept(
  o: Partial<InterceptSolution> = {},
): InterceptSolution {
  return {
    feasible: true,
    point: { x: 0.62, y: 0.44 },
    time_to_intercept: 1.4,
    launch_point: { x: 0.5, y: 1 },
    detail: "Intercept feasible in 1.4 s.",
    ...o,
  };
}

export function makeInterceptor(
  o: Partial<InterceptorState> = {},
): InterceptorState {
  return {
    phase: "FLIGHT",
    active: true,
    position: { x: 0.55, y: 0.7 },
    launch_point: { x: 0.5, y: 1 },
    aim_point: { x: 0.62, y: 0.44 },
    trail: [{ x: 0.5, y: 1 } as Point, { x: 0.52, y: 0.85 } as Point],
    progress: 0.5,
    time_since_launch: 0.7,
    time_to_intercept: 0.7,
    ...o,
  };
}

export function makeEvent(o: Partial<MissionEvent> = {}): MissionEvent {
  return {
    timestamp: 1_700_000_000,
    kind: "info",
    message: "Track acquired on UAV-001.",
    ...o,
  };
}

export function makeTelemetry(o: Partial<TelemetryFrame> = {}): TelemetryFrame {
  return {
    type: "telemetry",
    timestamp: 1_700_000_000,
    system: makeSystem(),
    mission: makeMission(),
    targets: [makeTarget()],
    detection: makeDetection(),
    intercept: makeIntercept(),
    interceptor: null,
    events: [],
    ...o,
  };
}

export function makeVideo(o: Partial<VideoInfo> = {}): VideoInfo {
  return {
    name: "demo_drone.mp4",
    path: "/assets/videos/demo_drone.mp4",
    size_mb: 2.6,
    duration: 24,
    width: 960,
    height: 540,
    fps: 25,
    is_active: false,
    uploaded: false,
    ...o,
  };
}

export function makeSourceStatus(o: Partial<SourceStatus> = {}): SourceStatus {
  return {
    video_source: "file",
    active_video: "demo_drone.mp4",
    camera_index: 0,
    detector: "motion",
    detection_threshold: 0.55,
    detectors_available: ["motion", "yolo"],
    videos: [makeVideo()],
    ...o,
  };
}

/** Every event kind, for exhaustive log-styling checks. */
export const ALL_EVENT_KINDS: EventKind[] = [
  "info",
  "detection",
  "track",
  "state",
  "authorization",
  "actuation",
  "warning",
  "error",
];

/** Every mission state, for exhaustive rendering checks. */
export const ALL_STATES: MissionState[] = [
  "SEARCHING",
  "DETECTED",
  "TRACKING",
  "THREAT_CONFIRMED",
  "FOLLOWING",
  "AWAITING_AUTHORIZATION",
  "AUTHORIZED",
  "ACTUATED",
  "TARGET_LOST",
  "ERROR",
];
