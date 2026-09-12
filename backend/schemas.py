"""Canonical API contract between backend and frontend.

This module is the single source of truth for every payload that crosses the
WebSocket or REST boundary. The TypeScript mirror in
`frontend/src/types.ts` is generated from this file by `scripts/gen_types.py`
- edit this module, then regenerate. Do not hand-edit the TypeScript.
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


class MissionPhase(str, Enum):
    """The seven operational phases shown on the mission timeline.

    Coarser than `MissionState` on purpose. The state machine has states an
    operator does not need on a timeline (TARGET_LOST is a setback, not a
    step), so the timeline is a *projection* of mission state, derived on the
    backend - see `backend.mission.timeline`. The frontend renders it and
    never computes its own progression.
    """

    SEARCH = "SEARCH"
    DETECT = "DETECT"
    TRACK = "TRACK"
    CONFIRM = "CONFIRM"
    FOLLOW = "FOLLOW"
    AUTHORIZE = "AUTHORIZE"
    LAUNCH = "LAUNCH"


class PhaseStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETE = "COMPLETE"


class PhaseProgress(BaseModel):
    """One step of the mission timeline."""

    phase: MissionPhase
    status: PhaseStatus
    # 0..1 within an ACTIVE phase, for the step's progress indicator.
    progress: float = 0.0


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
    speed a given image-plane motion implies - the two airframes differ by
    roughly an order of magnitude in size.
    """

    UNKNOWN = "UNKNOWN"
    MULTIROTOR = "MULTIROTOR"  # FPV quad - can hover, turn on the spot
    FIXED_WING = "FIXED_WING"  # Shahed-type - cannot hover, holds course


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

    target_id: str  # e.g. "UAV-001" - stable for the life of the track
    object_class: str = Field(serialization_alias="class")  # "uav"
    confidence: float
    bbox: BBox
    tracking: bool  # True once the track is confirmed (not tentative)
    age_frames: int
    track_duration: float  # seconds since first detection
    trail: list[Point] = Field(default_factory=list)
    is_primary: bool = False  # the target the mission is acting on
    trajectory: Trajectory | None = None  # predicted path (primary only)
    # Operator-facing view of the same extrapolation, scoped to the sensor
    # frame. The UI renders this; `trajectory` stays for the overlay geometry.
    projection: TrackProjection | None = None
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
    # aspect ratio so normalised bboxes land on the right pixels - without
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
    model is doing something before committing to a run - rather than staring
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
    # The timeline, derived from `state` on the backend so the operator screen
    # cannot disagree with the state machine about how far the mission has got.
    phase: MissionPhase = MissionPhase.SEARCH
    phases: list[PhaseProgress] = Field(default_factory=list)


class EventKind(str, Enum):
    """Severity/colour class of an event. Drives presentation only."""

    INFO = "info"
    DETECTION = "detection"
    TRACK = "track"
    STATE = "state"
    AUTHORIZATION = "authorization"
    ACTUATION = "actuation"
    WARNING = "warning"
    ERROR = "error"


class EventCode(str, Enum):
    """What actually happened, as a stable machine-readable code.

    `message` is prose for a human reading the console; `code` is what a
    field-test analysis script filters on. Codes are append-only: renaming
    one silently invalidates every recorded mission run that used it.
    """

    SYSTEM_START = "SYSTEM_START"
    SYSTEM_INFO = "SYSTEM_INFO"
    SOURCE_CHANGED = "SOURCE_CHANGED"
    SENSOR_LOST = "SENSOR_LOST"
    SENSOR_RESTORED = "SENSOR_RESTORED"

    OBJECT_DETECTED = "OBJECT_DETECTED"
    TRACK_CREATED = "TRACK_CREATED"
    TRACK_CONFIRMED = "TRACK_CONFIRMED"
    TRACK_LOST = "TRACK_LOST"
    TRACK_REACQUIRED = "TRACK_REACQUIRED"

    THREAT_CRITERIA_MET = "THREAT_CRITERIA_MET"
    FOLLOWING_TARGET = "FOLLOWING_TARGET"

    ENGAGEMENT_READY = "ENGAGEMENT_READY"
    ENGAGEMENT_NOT_READY = "ENGAGEMENT_NOT_READY"
    AUTHORIZATION_REQUESTED = "AUTHORIZATION_REQUESTED"
    AUTHORIZATION_REJECTED = "AUTHORIZATION_REJECTED"
    OPERATOR_AUTHORIZED = "OPERATOR_AUTHORIZED"

    LAUNCH_COMMAND_ISSUED = "LAUNCH_COMMAND_ISSUED"
    ACTUATOR_ACKNOWLEDGED = "ACTUATOR_ACKNOWLEDGED"
    ACTUATOR_REJECTED = "ACTUATOR_REJECTED"
    LAUNCHER_SAFED = "LAUNCHER_SAFED"
    INTERCEPTOR_RELEASE_SIMULATED = "INTERCEPTOR_RELEASE_SIMULATED"

    MISSION_RESET = "MISSION_RESET"
    STATE_CHANGE = "STATE_CHANGE"
    WARNING = "WARNING"
    ERROR = "ERROR"


class MissionEvent(BaseModel):
    """One timestamped entry in the operator event log."""

    timestamp: float  # unix seconds
    kind: EventKind
    message: str
    code: EventCode = EventCode.SYSTEM_INFO
    target_id: str | None = None


# ======================================================================
# Canister subsystem model
# ======================================================================


class SubsystemId(str, Enum):
    """The subsystems a deployed canister reports on."""

    SYSTEM = "SYSTEM"
    SENSOR = "SENSOR"
    PERCEPTION = "PERCEPTION"
    TRACKER = "TRACKER"
    COMPUTE = "COMPUTE"
    LINK = "LINK"
    LAUNCHER = "LAUNCHER"
    INTERCEPTOR = "INTERCEPTOR"
    POWER = "POWER"
    TEMPERATURE = "TEMPERATURE"


class SubsystemState(str, Enum):
    """Reported condition of one subsystem.

    The "unknown" members are deliberate and load-bearing: V0 has no power
    rail and no thermistor, and inventing a plausible battery percentage is
    the single easiest way to make the whole status panel untrustworthy. A
    subsystem with no sensor says so.
    """

    OPERATIONAL = "OPERATIONAL"
    ONLINE = "ONLINE"
    LOCAL = "LOCAL"
    SAFE = "SAFE"
    ARMED = "ARMED"
    STOWED = "STOWED"
    INITIALISING = "INITIALISING"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    FAULT = "FAULT"
    NOT_AVAILABLE = "N/A"
    NOT_CONNECTED = "NOT CONNECTED"
    NOT_CALIBRATED = "NOT CALIBRATED"


class Subsystem(BaseModel):
    """One line of the canister status panel."""

    id: SubsystemId
    label: str
    state: SubsystemState
    detail: str = ""
    # True when the value came from a real hardware sensor. Everything in V0
    # is False except what the software genuinely knows about itself. This is
    # the flag a future hardware build flips, and the UI marks the difference.
    measured: bool = False
    # Whether this state counts as healthy, so the UI does not have to encode
    # which SubsystemState values are good for which subsystem.
    nominal: bool = True


class CanisterStatus(BaseModel):
    """What CANISTER 01 currently knows about itself."""

    canister_id: str = "CANISTER 01"
    # Rolled up from the subsystems: OPERATIONAL, DEGRADED or OFFLINE.
    state: SubsystemState = SubsystemState.INITIALISING
    detail: str = ""
    uptime: float = 0.0  # seconds since the canister came up
    subsystems: list[Subsystem] = Field(default_factory=list)


# ======================================================================
# Engagement readiness  →  launch command  →  actuator
# ======================================================================


class ReadinessState(str, Enum):
    """The single derived state gating an engagement.

    The progression is strictly one-way within an engagement:
    NOT_READY → READY_FOR_AUTHORIZATION → AUTHORIZED → LAUNCH_COMMAND_ISSUED.
    """

    NOT_READY = "NOT_READY"
    READY_FOR_AUTHORIZATION = "READY_FOR_AUTHORIZATION"
    AUTHORIZED = "AUTHORIZED"
    LAUNCH_COMMAND_ISSUED = "LAUNCH_COMMAND_ISSUED"


class ReadinessCondition(BaseModel):
    """One named precondition, with the evidence for its verdict."""

    name: str
    met: bool
    detail: str = ""


class EngagementReadiness(BaseModel):
    """Deterministic, inspectable engagement preconditions.

    This sits immediately upstream of the launcher boundary. Every condition
    is a pure function of state the operator can also see, and the blocking
    ones are named - an operator is never told "not ready" without being told
    which condition failed.
    """

    state: ReadinessState = ReadinessState.NOT_READY
    conditions: list[ReadinessCondition] = Field(default_factory=list)
    blocking: list[str] = Field(default_factory=list)
    detail: str = ""


class LauncherState(str, Enum):
    """Launcher interface state.

    >>> SAFETY <<< In V0 the launcher is a simulated interface. These states
    describe a software handshake, not a physical mechanism.
    """

    SAFE = "SAFE"
    ARMED = "ARMED"
    COMMAND_RECEIVED = "COMMAND_RECEIVED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    SPENT = "SPENT"
    FAULT = "FAULT"


class LaunchCommand(BaseModel):
    """The command handed across the launcher boundary.

    This model *is* the hardware integration seam. A future validated
    launcher controller consumes exactly this and returns a
    `LaunchAcknowledgement`; nothing upstream of it - perception, tracking,
    mission logic or the UI - changes when that happens.

    >>> SAFETY <<< Issuing this in V0 produces a log entry, a telemetry
    event and an animation. It commands no physical device.
    """

    command_id: str
    issued_at: float
    target_id: str | None = None
    mission_state: MissionState
    readiness: ReadinessState
    # Recorded so the mission report can show what the operator authorized
    # against, not merely that they pressed a button.
    authorized_by: str = "OPERATOR"
    authorized_at: float = 0.0
    simulated: bool = True


class LaunchAcknowledgement(BaseModel):
    """The launcher's reply. Absence of one is itself a reportable fault."""

    command_id: str
    actuator: str
    accepted: bool
    acknowledged_at: float
    latency_ms: float = 0.0
    launcher_state: LauncherState = LauncherState.SAFE
    detail: str = ""


class LauncherStatus(BaseModel):
    """Launcher interface health and history, for telemetry."""

    interface: str = "simulated"
    state: LauncherState = LauncherState.SAFE
    # False only when a real launcher controller is attached.
    simulated: bool = True
    ready: bool = True
    commands_issued: int = 0
    last_command_id: str | None = None
    last_command_at: float | None = None
    last_acknowledged_at: float | None = None
    detail: str = "Simulated launcher interface. No physical device attached."


# ======================================================================
# Track projection (sensor frame - NOT a firing solution)
# ======================================================================


class TrackStability(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    UNSTABLE = "UNSTABLE"
    SETTLING = "SETTLING"
    STABLE = "STABLE"


class TrackProjection(BaseModel):
    """Where the track is heading, expressed in the sensor frame.

    >>> SCOPE <<< This is an extrapolation of observed image-plane motion.
    It is not a range, not a ground track, not an impact prediction and not a
    firing solution. Every field is relative to the camera frame, and the UI
    labels it as such.
    """

    valid: bool = False
    frame: Literal["SENSOR_FRAME"] = "SENSOR_FRAME"
    # Direction of travel within the frame, degrees clockwise from frame-up.
    # None when there is not enough motion to call one.
    direction_deg: float | None = None
    direction_label: str = "-"
    stability: TrackStability = TrackStability.UNAVAILABLE
    horizon: float = 0.0  # seconds the projection extends
    confidence: float = 0.0  # 0..1, from fit residual and history length
    points: list[TrajectoryPoint] = Field(default_factory=list)


# ======================================================================
# Tactical picture
# ======================================================================


class TacticalFrame(str, Enum):
    """Which reference frame the tactical picture is expressed in.

    V0 has exactly one: the sensor frame. The enum exists so that adding a
    geodetic source later is a new member and a new producer, not a rewrite
    of the view - the view switches on this field.
    """

    SENSOR_FRAME = "SENSOR_FRAME"


class TacticalTrack(BaseModel):
    """One track as plotted on the tactical view.

    Positions are *relative sensor-frame* quantities, normalised. Bearing and
    range in real units are present but null unless the sensor is calibrated;
    `bearing_available` / `range_available` say which, so the view renders an
    honest relative picture today and absolute geometry the day a calibrated
    sensor or an external track source provides it.
    """

    target_id: str
    is_primary: bool = False
    # -1 (left frame edge) .. +1 (right frame edge), 0 = boresight.
    bearing_norm: float = 0.0
    # 0 (top of frame) .. 1 (bottom of frame).
    elevation_norm: float = 0.0
    # Apparent size as a fraction of frame width - a *relative* proximity
    # cue, deliberately not converted into a distance.
    apparent_size: float = 0.0
    # Unit vector of travel in the sensor frame, for the track vector arrow.
    course_x: float = 0.0
    course_y: float = 0.0
    speed_norm: float = 0.0  # frame widths per second

    bearing_available: bool = False
    bearing_deg: float | None = None
    range_available: bool = False
    range_m: float | None = None

    # Where the track is projected to go, as a list of future bearing/elevation
    # pairs (`x` = bearing_norm, `y` = elevation_norm). Bearing only: range
    # cannot be extrapolated because it was never measured, so the plotted
    # path holds the track's current depth rather than inventing a closing rate.
    path: list[Point] = Field(default_factory=list)

    confidence: float = 0.0
    platform: PlatformClass = PlatformClass.UNKNOWN
    track_duration: float = 0.0
    # Which sensor or canister reported this track. One entry today; the
    # field exists so a second canister's tracks can be plotted and
    # distinguished without changing the model.
    source: str = "CANISTER_01/SENSOR_01"


class TacticalPicture(BaseModel):
    """The local tactical picture, honestly scoped.

    >>> SCOPE <<< No GPS, no geographic reference, no absolute bearing. This
    is what one uncalibrated camera can support: relative position within its
    own field of view.
    """

    frame: TacticalFrame = TacticalFrame.SENSOR_FRAME
    frame_label: str = "LOCAL TRACK · RELATIVE COORDINATES · SENSOR FRAME"
    # Sensor horizontal field of view, degrees - null unless configured, in
    # which case the sector is drawn to scale rather than indicatively.
    fov_deg: float | None = None
    calibrated: bool = False
    # Confirmed tracks only. Tentative detections are counted, not plotted -
    # see `candidates`.
    tracks: list[TacticalTrack] = Field(default_factory=list)
    # How many detections the tracker is holding but has not yet confirmed.
    # Reported as a number so the operator knows the sensor is busy, without
    # the plot filling with unidentified marks.
    candidates: int = 0
    sources: list[str] = Field(default_factory=lambda: ["CANISTER_01/SENSOR_01"])


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

    # ---- operational canister state ----
    canister: CanisterStatus = Field(default_factory=CanisterStatus)
    readiness: EngagementReadiness = Field(default_factory=EngagementReadiness)
    launcher: LauncherStatus = Field(default_factory=LauncherStatus)
    tactical: TacticalPicture = Field(default_factory=TacticalPicture)


class CommandResponse(BaseModel):
    """Reply to an operator command (authorize / reset)."""

    ok: bool
    state: MissionState
    detail: str
    readiness: ReadinessState = ReadinessState.NOT_READY


# `Target` refers to `TrackProjection`, which is declared after it so the
# operational models stay grouped. Rebuild it explicitly rather than relying
# on Pydantic's lazy resolution, which would otherwise surface as a
# confusing error on the first serialisation rather than at import.
Target.model_rebuild()
