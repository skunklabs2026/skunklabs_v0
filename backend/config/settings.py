"""Central configuration for SkunkLabs MVP V0.

Every tunable threshold in the demo lives here. Nothing else in the codebase
should hardcode a number that an operator might reasonably want to change
between demo runs.

All values can be overridden with SKUNK_-prefixed environment variables, or by
a .env file next to the repository root. See .env.example.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SKUNK_",
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------------- Video source ----------------
    # "file" replays a recorded clip (repeatable — the demo default).
    # "camera" opens a USB/built-in camera.
    video_source: Literal["file", "camera"] = "file"
    video_path: Path = REPO_ROOT / "assets" / "videos" / "demo_drone.mp4"
    camera_index: int = 0
    # Frames per second the pipeline aims to process. The file source paces
    # itself to this; the camera source just reads as fast as it can.
    target_fps: float = 25.0
    # Long side the frame is resized to before detection. Smaller == faster.
    frame_width: int = 960
    # Replay the clip from the start when it ends, so the demo can loop.
    loop_video: bool = True
    # JPEG quality for the MJPEG preview stream sent to the browser.
    jpeg_quality: int = 80

    # ---------------- Detector ----------------
    # "motion" — pure OpenCV background subtraction. No model weights, no
    #            torch. Extremely reliable for an airborne object against
    #            sky, which is exactly the V0 scenario. This is the default
    #            because the V0 priority is repeatability.
    # "yolo"   — Ultralytics YOLO26n. Requires requirements-yolo.txt.
    detector: Literal["motion", "yolo"] = "motion"
    detection_threshold: float = 0.55
    # YOLO gets its own, lower default. COCO confidences for a small, distant
    # object against flat sky sit well below what the motion heuristic
    # produces, so sharing one threshold silently suppresses real detections.
    yolo_detection_threshold: float = 0.25

    # -- yolo detector --
    model_path: str = "yolo26n.pt"
    # Apple Silicon: "mps" uses the GPU, "cpu" is the portable fallback,
    # "auto" picks the best available.
    device: Literal["auto", "mps", "cpu"] = "auto"
    # Generic COCO-pretrained models have no "drone" class. These are the
    # classes that, in the V0 demo scenario, correspond to an airborne UAV.
    # Anything detected as one of these is relabelled "uav".
    uav_class_names: tuple[str, ...] = ("airplane", "bird", "kite", "frisbee")

    # -- motion detector --
    # Contours smaller/larger than these (fraction of frame area) are ignored,
    # which rejects both sensor noise and whole-frame lighting changes.
    motion_min_area_frac: float = 0.00035
    motion_max_area_frac: float = 0.08
    motion_history: int = 240
    motion_var_threshold: float = 40.0
    # Frames to let the background model settle before trusting detections.
    motion_warmup_frames: int = 12

    # ---------------- Tracker ----------------
    # IoU below which a detection is never associated with an existing track.
    track_iou_threshold: float = 0.20
    # A track survives this many frames with no matching detection before it
    # is dropped. At 25 fps this is ~1.2 s of tolerated occlusion, which stops
    # the state machine flickering on a brief detection dropout.
    track_max_age: int = 30
    # Consecutive hits before a tentative track is promoted to confirmed.
    track_min_hits: int = 3
    # Number of past centre points retained for the UI trajectory tail.
    track_trail_length: int = 48
    # Proximity-gate radius, in multiples of target size, for associating a
    # fast target whose boxes no longer overlap frame to frame. 0 disables.
    track_gate_scale: float = 4.0

    # ---------------- Mission rules (V0 demo logic) ----------------
    # A track must be held for this long, above this confidence, and be
    # classified as a UAV, before the demo declares THREAT_CONFIRMED.
    # These are demo criteria, NOT a real threat-identification capability.
    confirmation_time: float = 2.0
    confirmation_confidence: float = 0.60
    confirmation_classes: tuple[str, ...] = ("uav",)
    # Seconds a confirmed target must be followed before the operator is
    # offered the AUTHORIZE control.
    follow_time: float = 1.5
    # Seconds with no track before the mission falls back to TARGET_LOST.
    target_lost_grace: float = 1.0
    # Seconds TARGET_LOST is displayed before returning to SEARCHING.
    target_lost_hold: float = 2.5
    # Seconds the ACTUATED state is held before the demo auto-resets.
    # Set to 0 to require a manual reset.
    actuated_hold: float = 6.0

    # ---------------- Platform classification ----------------
    # FPV multirotor vs fixed-wing, from track kinematics. Determines the
    # prediction horizon and the assumed airframe size used for speed.
    # ~3.6s at 25 fps. Chosen empirically: a shorter window sees only one
    # leg of a weaving flight, which looks straight, and the classifier then
    # flips between the two airframes roughly 50/50. Several seconds are
    # needed for a manoeuvre signature to actually appear.
    platform_window: int = 90  # observations retained per track
    platform_min_samples: int = 12  # before any classification is attempted
    platform_hover_speed: float = 0.02  # frame widths/s counted as hovering
    platform_straight_threshold: float = 0.93  # straightness -> fixed-wing
    platform_speed_cv_threshold: float = 0.35  # speed steadiness
    platform_turn_rate_threshold: float = 35.0  # deg/s -> multirotor
    platform_commit_frames: int = 8  # consistent votes before committing

    # ---------------- Speed assessment ----------------
    # Horizontal field of view of the sensor, degrees. Absolute speed in m/s
    # is only reported when this is set — without it the geometry is
    # unconstrained and any figure would be invented. 0 disables.
    camera_hfov_deg: float = 0.0

    # ---------------- Performance ----------------
    # Run the detector every Nth frame and let the tracker coast in between.
    # 1 = detect every frame. 2-3 roughly doubles throughput with a neural
    # detector at negligible tracking cost for smooth motion.
    detection_stride: int = 1
    # Width the frame is downscaled to *for inference only*; the displayed
    # frame keeps `frame_width`. 0 disables the extra downscale.
    inference_width: int = 0

    # ---------------- Trajectory prediction ----------------
    # Image-plane extrapolation for display. Not a flight model, not guidance.
    # Seconds ahead the predicted path extends.
    trajectory_horizon: float = 2.0
    # Points sampled along the prediction (UI resolution).
    trajectory_samples: int = 16
    # Observations used for the fit. ~1s of history at 25 fps.
    trajectory_window: int = 24
    # Fit residual (normalised units) at which confidence reaches zero.
    trajectory_max_residual: float = 0.02

    # ---------------- Intercept estimate (display only) ----------------
    # Notional canister position in normalised frame coordinates.
    # (0.5, 1.0) is bottom-centre — the camera sits on the canister.
    launch_point_x: float = 0.5
    launch_point_y: float = 1.0
    # Notional interceptor speed, in normalised frame widths per second.
    interceptor_speed: float = 0.85
    # Minimum trajectory confidence before an intercept is offered.
    intercept_min_confidence: float = 0.25

    # ---------------- Video library ----------------
    # Directory scanned for selectable clips, and where uploads are stored.
    video_library_dir: Path = REPO_ROOT / "assets" / "videos"
    upload_dir: Path = REPO_ROOT / "assets" / "videos" / "uploads"
    max_upload_mb: int = 2048
    allowed_video_suffixes: tuple[str, ...] = (
        ".mp4",
        ".mov",
        ".m4v",
        ".avi",
        ".mkv",
        ".webm",
    )

    # ---------------- Actuation ----------------
    # "simulated" — logs the event and emits it over the WebSocket. Safe.
    actuator: Literal["simulated"] = "simulated"
    # Seconds the actuator takes to report completion, so the UI can play a
    # launch cue rather than snapping instantly to done.
    actuator_duration: float = 1.6

    # ---------------- Server ----------------
    # Loopback by design, not by accident. POST /api/source/video accepts any
    # absolute path on this machine and reports whether it exists and decodes
    # — harmless from localhost, a file probe from the network. Changing this
    # to 0.0.0.0 exposes that endpoint; see README, "Configuration".
    host: str = "127.0.0.1"
    port: int = 8000
    # Origins allowed to call the API. The Vite dev server runs on 5173.
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    log_level: str = "INFO"
    # Number of recent events retained in memory for the operator event log.
    event_log_size: int = 200
    # Built frontend. When this directory exists the backend serves the
    # console itself, so production runs as a single process on one origin.
    # In development Vite serves it instead and this is simply absent.
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"


@lru_cache
def get_settings() -> Settings:
    return Settings()
