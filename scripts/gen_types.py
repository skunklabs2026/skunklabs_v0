"""Generate the frontend's TypeScript API contracts from the backend models.

    backend/scenario/models.py  ->  frontend/src/scenario/contract.ts   (V0 launcher demo)
    backend/schemas.py          ->  frontend/src/types.ts               (video sensor lab)

Keeps one canonical API contract per surface. Run it after changing any schema:

    python scripts/gen_types.py

Deliberately a small bespoke emitter rather than a JSON-Schema toolchain: the
contract is a dozen models, and this keeps the dependency list short, which
is a stated V0 priority.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import types  # noqa: E402
import typing  # noqa: E402
from enum import Enum  # noqa: E402

from pydantic import BaseModel  # noqa: E402

from backend.scenario import models as scenario_models  # noqa: E402
from backend.schemas import (  # noqa: E402
    EventCode,
    EventKind,
    InterceptorPhase,
    LauncherState,
    MissionPhase,
    MissionState,
    PhaseStatus,
    PlatformClass,
    ReadinessState,
    SubsystemId,
    SubsystemState,
    TacticalFrame,
    TrackStability,
)

OUTPUT = REPO_ROOT / "frontend" / "src" / "types.ts"
SCENARIO_OUTPUT = REPO_ROOT / "frontend" / "src" / "scenario" / "contract.ts"

SCENARIO_HEADER = """// GENERATED FILE - do not edit by hand.
// Source of truth: backend/scenario/models.py
// Regenerate with:  python scripts/gen_types.py
"""


def _ts_type(annotation: object) -> str:
    """TypeScript for one Pydantic field annotation."""
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        return " | ".join(
            "null" if arg is type(None) else _ts_type(arg)
            for arg in typing.get_args(annotation)
        )
    if origin is list:
        (item,) = typing.get_args(annotation)
        inner = _ts_type(item)
        return f"({inner})[]" if "|" in inner else f"{inner}[]"
    if origin is typing.Literal:
        return " | ".join(f'"{value}"' for value in typing.get_args(annotation))
    if isinstance(annotation, type) and issubclass(annotation, (Enum, BaseModel)):
        return annotation.__name__
    primitives = {str: "string", int: "number", float: "number", bool: "boolean"}
    if annotation in primitives:
        return primitives[annotation]
    raise TypeError(f"No TypeScript mapping for {annotation!r}")


def interface_block(model: type[BaseModel]) -> str:
    fields = "\n".join(
        f"  {name}: {_ts_type(field.annotation)};" for name, field in model.model_fields.items()
    )
    return f"export interface {model.__name__} {{\n{fields}\n}}\n"


def scenario_contract() -> str:
    """Every enum and model in backend/scenario/models.py, in declaration order."""
    members = [
        value
        for value in vars(scenario_models).values()
        if isinstance(value, type)
        and value.__module__ == scenario_models.__name__
        and issubclass(value, (Enum, BaseModel))
    ]
    blocks = [
        enum_block(m.__name__, m) if issubclass(m, Enum) else interface_block(m)
        for m in members
    ]
    return "\n".join([SCENARIO_HEADER, *blocks])


HEADER = """// GENERATED FILE - do not edit by hand.
// Source of truth: backend/schemas.py
// Regenerate with:  python scripts/gen_types.py
"""

BODY = """
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
  /** Frame widths per second - always present, a direct measurement. */
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
  /** Derived on the backend - the UI renders it, it never computes one. */
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
  /** Detections held but not yet confirmed - counted, not plotted. */
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
"""


def enum_block(name: str, enum_cls) -> str:
    members = "\n".join(f'  | "{m.value}"' for m in enum_cls)
    return f"export type {name} =\n{members};\n"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(
        [
            HEADER,
            enum_block("MissionState", MissionState),
            enum_block("MissionPhase", MissionPhase),
            enum_block("PhaseStatus", PhaseStatus),
            enum_block("EventKind", EventKind),
            enum_block("EventCode", EventCode),
            enum_block("InterceptorPhase", InterceptorPhase),
            enum_block("PlatformClass", PlatformClass),
            enum_block("SubsystemId", SubsystemId),
            enum_block("SubsystemState", SubsystemState),
            enum_block("ReadinessState", ReadinessState),
            enum_block("LauncherState", LauncherState),
            enum_block("TrackStability", TrackStability),
            enum_block("TacticalFrame", TacticalFrame),
            BODY.strip(),
            "",
        ]
    )
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(REPO_ROOT)}")

    SCENARIO_OUTPUT.write_text(scenario_contract(), encoding="utf-8")
    print(f"Wrote {SCENARIO_OUTPUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
