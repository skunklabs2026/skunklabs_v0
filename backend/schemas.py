"""Canonical API contract between backend and frontend.

This module is the single source of truth for every payload that crosses the
WebSocket or REST boundary. The TypeScript mirror in
`frontend/src/types.ts` is generated from this file by `scripts/gen_types.py`
— edit this module, then regenerate. Do not hand-edit the TypeScript.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class MissionState(str, Enum):
    """The operational states of the V0 mission state machine."""

    SEARCHING = "SEARCHING"
    DETECTED = "DETECTED"
    TRACKING = "TRACKING"
    THREAT_CONFIRMED = "THREAT_CONFIRMED"
    FOLLOWING = "FOLLOWING"
    AWAITING_AUTHORIZATION = "AWAITING_AUTHORIZATION"
    AUTHORIZED = "AUTHORIZED"
    ACTUATED = "ACTUATED"
    TARGET_LOST = "TARGET_LOST"
    ERROR = "ERROR"


class BBox(BaseModel):
    """Axis-aligned box in *normalised* frame coordinates (0..1).

    Normalised so the frontend can overlay boxes on a video element of any
    rendered size without knowing the source resolution.
    """

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(ge=0.0, le=1.0)
    height: float = Field(ge=0.0, le=1.0)


class Point(BaseModel):
    """A normalised point, used for track trails."""

    x: float
    y: float


class PlatformClass(str, Enum):
    """Airframe class inferred from track kinematics.

    Drives both how far ahead the trajectory is predicted and what absolute
    speed a given image-plane motion implies — the two airframes differ by
    roughly an order of magnitude in size.
    """

    UNKNOWN = "UNKNOWN"
    MULTIROTOR = "MULTIROTOR"  # FPV quad — can hover, turn on the spot
    FIXED_WING = "FIXED_WING"  # Shahed-type — cannot hover, holds course


class PlatformFeatures(BaseModel):
    """The kinematic evidence behind a classification, so it is inspectable."""

    straightness: float = 0.0  # net displacement / path length
    speed_cv: float = 0.0  # coefficient of variation of speed
    turn_rate: float = 0.0  # mean heading change, deg/s
    hover_fraction: float = 0.0  # fraction of samples near-stationary
    mean_speed: float = 0.0  # normalised frame widths / second
    samples: int = 0


class SpeedEstimate(BaseModel):
    """Assessed target speed.

    Absolute speed cannot be measured from a single uncalibrated camera. It
    is *inferred* by assuming the airframe's characteristic size, which is
    why the platform classification matters: an FPV quad and a fixed-wing
    subtending the same pixels are at very different ranges, and therefore
    very different speeds.

    `available` is False unless the camera field of view is configured.
    """

    available: bool = False
    image_speed: float = 0.0  # normalised frame widths per second (always)
    range_m: float = 0.0  # inferred range, metres
    speed_ms: float = 0.0  # inferred cross-range speed, metres/second
    speed_kmh: float = 0.0
    assumed_size_m: float = 0.0
    plausible: bool = True  # within the class's typical speed band
    detail: str = ""


class Velocity(BaseModel):
    """Normalised frame-units per second."""

    x: float
    y: float
    speed: float  # magnitude, normalised units/s


class TrajectoryPoint(BaseModel):
    """A predicted future position."""

    x: float
    y: float
    t: float  # seconds ahead of the current frame


class Trajectory(BaseModel):
    """Short-horizon predicted path of a target.

    This is a kinematic extrapolation of observed image-plane motion, not a
    flight model. It says where the object is heading if it keeps doing what
    it is doing.
    """

    valid: bool
    points: list[TrajectoryPoint] = Field(default_factory=list)
    velocity: Velocity | None = None
    # Mean fit residual in normalised units; lower is a steadier track.
    residual: float = 0.0
    # 0..1 confidence in the extrapolation, from fit quality and history.
    confidence: float = 0.0
    horizon: float = 0.0  # seconds the prediction extends


class InterceptSolution(BaseModel):
    """Where and when a notional interceptor could meet the target.

    A geometric estimate in image space for demonstration and display only.
    It is not guidance, and nothing acts on it.
    """

    feasible: bool
    point: Point | None = None
    time_to_intercept: float = 0.0  # seconds
    launch_point: Point | None = None
    detail: str = ""


class Target(BaseModel):
    """One tracked target as presented to the operator."""

    target_id: str  # e.g. "UAV-001" — stable for the life of the track
    object_class: str = Field(serialization_alias="class")  # "uav"
    confidence: float
    bbox: BBox
    tracking: bool  # True once the track is confirmed (not tentative)
    age_frames: int
    track_duration: float  # seconds since first detection
    trail: list[Point] = Field(default_factory=list)
    is_primary: bool = False  # the target the mission is acting on
    trajectory: Trajectory | None = None  # predicted path (primary only)
    platform: PlatformClass = PlatformClass.UNKNOWN
    platform_label: str = "Unclassified"
    platform_features: PlatformFeatures | None = None
    speed: SpeedEstimate | None = None


class SystemStatus(BaseModel):
    """Health of the sensing chain, for the canister status panel."""

    sensor_online: bool
    detector: str  # "motion" | "yolo"
    detector_ready: bool
    video_source: str  # "file" | "camera"
    fps: float
    frame_index: int
    # Source frame dimensions. The UI sizes the overlay box to this exact
    # aspect ratio so normalised bboxes land on the right pixels — without
    # it, letterboxing offsets every overlay from the object it marks.
    frame_width: int = 0
    frame_height: int = 0


class ClassCount(BaseModel):
    """How often one class has been detected recently."""

    name: str
    count: int


class DetectionStats(BaseModel):
    """Evidence that the detector is actually working on the current source.

    This exists so an operator loading unfamiliar footage can confirm the
    model is doing something before committing to a run — rather than staring
    at an empty frame and guessing whether the video, the detector, or the
    thresholds are at fault.
    """

    detections_last_frame: int = 0
    detections_total: int = 0
    frames_processed: int = 0
    # Classes seen over the recent window, most frequent first.
    classes: list[ClassCount] = Field(default_factory=list)
    # Mean detector time per frame, milliseconds.
    latency_ms: float = 0.0
    active_tracks: int = 0


class MissionStatus(BaseModel):
    """Authoritative mission state. The UI renders this; it never invents it."""

    state: MissionState
    target_id: str | None = None
    authorization_required: bool = False
    can_authorize: bool = False
    # Human-readable one-liner shown under the big state banner.
    detail: str = ""
    # 0..1 progress toward the next automatic transition, for UI progress
    # rings (e.g. how far through CONFIRMATION_TIME the track is).
    progress: float = 0.0
    state_since: float = 0.0  # seconds the mission has held this state


class EventKind(str, Enum):
    INFO = "info"
    DETECTION = "detection"
    TRACK = "track"
    STATE = "state"
    AUTHORIZATION = "authorization"
    ACTUATION = "actuation"
    WARNING = "warning"
    ERROR = "error"


class MissionEvent(BaseModel):
    """One timestamped entry in the operator event log."""

    timestamp: float  # unix seconds
    kind: EventKind
    message: str


class InterceptorPhase(str, Enum):
    """Phases of the simulated interceptor event."""

    IDLE = "IDLE"
    LAUNCH = "LAUNCH"
    FLIGHT = "FLIGHT"
    INTERCEPT = "INTERCEPT"
    SPENT = "SPENT"  # flight complete, awaiting reset


class InterceptorState(BaseModel):
    """The simulated interceptor, for display.

    >>> SAFETY <<< This describes an animation and a log entry. No physical
    device is commanded, and nothing here constitutes guidance.
    """

    phase: InterceptorPhase = InterceptorPhase.IDLE
    active: bool = False
    position: Point | None = None
    launch_point: Point | None = None
    aim_point: Point | None = None  # where it is flying to
    trail: list[Point] = Field(default_factory=list)
    progress: float = 0.0  # 0..1 along the flight
    time_since_launch: float = 0.0
    time_to_intercept: float = 0.0


class VideoInfo(BaseModel):
    """One selectable video in the local library."""

    name: str
    path: str
    size_mb: float
    duration: float = 0.0  # seconds, 0 if unknown
    width: int = 0
    height: int = 0
    fps: float = 0.0
    is_active: bool = False
    uploaded: bool = False  # True for operator-supplied files


class SourceStatus(BaseModel):
    """Current input configuration, and what else is available."""

    video_source: str  # "file" | "camera"
    active_video: str | None = None
    camera_index: int = 0
    detector: str = "motion"
    detection_threshold: float = 0.0
    detectors_available: list[str] = Field(default_factory=list)
    videos: list[VideoInfo] = Field(default_factory=list)


class TelemetryFrame(BaseModel):
    """The per-frame payload pushed over the WebSocket.

    One message type carries everything the operator screen needs, so the UI
    can never render a half-updated mix of two different frames.
    """

    type: Literal["telemetry"] = "telemetry"
    timestamp: float
    system: SystemStatus
    mission: MissionStatus
    targets: list[Target]
    detection: DetectionStats = Field(default_factory=DetectionStats)
    intercept: InterceptSolution | None = None
    interceptor: InterceptorState | None = None
    # Only events new since the previous frame, so the client appends.
    events: list[MissionEvent] = Field(default_factory=list)


class ActuationResult(BaseModel):
    """Outcome of a safe, simulated actuation."""

    actuator: str
    ok: bool
    detail: str
    target_id: str | None = None
    timestamp: float


class CommandResponse(BaseModel):
    """Reply to an operator command (authorize / reset)."""

    ok: bool
    state: MissionState
    detail: str
