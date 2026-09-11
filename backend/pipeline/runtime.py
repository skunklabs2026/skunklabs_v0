"""The mission pipeline orchestrator.

Owns the single frame loop that drives the whole demo:

    video -> perception -> engagement -> telemetry

and nothing else. Each arrow is a separate module with one job; this file
is the thread, the loop, and the wiring between them. It runs on a worker
thread so that blocking OpenCV and inference calls never stall the asyncio
event loop serving the API.

Everything about this loop is written to fail soft. A detector exception, a
dropped camera, or a corrupt frame degrades the demo — it does not stop it.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

from backend.canister.status import CanisterInputs, CanisterStatusModel
from backend.config.settings import Settings
from backend.mission.recording import MissionRecorder
from backend.mission.tactical import build_tactical_picture
from backend.pipeline.engagement import EngagementStage
from backend.pipeline.hub import TelemetryHub
from backend.pipeline.inputs import InputController
from backend.pipeline.perception import PerceptionStage
from backend.schemas import (
    CanisterStatus,
    EventCode,
    EventKind,
    MissionEvent,
    MissionState,
    SourceStatus,
    SystemStatus,
    TelemetryFrame,
)
from backend.video.library import VideoLibrary

log = logging.getLogger(__name__)


class MissionPipeline:
    """Runs the perception + mission loop and publishes telemetry.

    The public surface is deliberately narrow: lifecycle (`start`/`stop`),
    operator commands, input selection, and reads. The API layer touches
    only these, never the stages behind them.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        self.hub = TelemetryHub(event_log_size=settings.event_log_size)
        self.library = VideoLibrary(
            settings.video_library_dir,
            settings.upload_dir,
            allowed_suffixes=settings.allowed_video_suffixes,
            max_upload_mb=settings.max_upload_mb,
        )

        self.inputs = InputController(settings, self.library, self.hub.emit, self.hub.lock)
        self.perception = PerceptionStage(settings)
        self.engagement = EngagementStage(settings, self.hub.emit)

        # The canister's model of itself, and the record of what it did.
        self.canister = CanisterStatusModel(canister_id=settings.canister_id)
        self.recorder = MissionRecorder(settings.runs_dir, enabled=settings.record_runs)
        self.hub.observe(self.recorder.record_event)

        # Loop bookkeeping.
        self._frame_index = 0
        self._fps = 0.0
        self._fps_samples: deque[float] = deque(maxlen=30)
        self._frame_size = (0, 0)  # (width, height)
        # Last mission state written to the run report, so a transition is
        # recorded once rather than on every frame that holds the state.
        self._recorded_state: MissionState | None = None

        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------
    # Convenience accessors, so callers do not reach through two objects
    # ------------------------------------------------------------------

    @property
    def video(self):
        return self.inputs.video

    @property
    def detector(self):
        return self.perception.detector

    @property
    def mission(self):
        return self.engagement.mission

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self.video.open()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="mission-pipeline", daemon=True)
        self._thread.start()
        self._begin_run()
        self.hub.emit(
            EventKind.INFO,
            f"{self.settings.canister_id} online. Sensor active, perception running.",
            code=EventCode.SYSTEM_START,
        )
        log.info(
            "Pipeline started: source=%s detector=%s",
            self.video.describe,
            self.detector.name,
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        # Close the report before releasing the source, so a shutdown mid-run
        # still leaves a usable record on disk.
        self.recorder.finish(reason="shutdown")
        self.video.release()
        self.perception.close()
        log.info("Pipeline stopped")

    def _begin_run(self) -> None:
        """Open a mission report for the current source and detector."""
        with self.hub.lock:
            self.recorder.start(
                source=self.video.describe,
                detector=self.detector.name,
            )
            self._recorded_state = None

    # ------------------------------------------------------------------
    # Operator commands (API thread)
    # ------------------------------------------------------------------

    def authorize(self) -> tuple[bool, str]:
        """Record operator authorization. Rejected unless the gate is open."""
        with self.hub.lock:
            accepted, detail = self.engagement.authorize()
            if accepted:
                # Capture the readiness the operator authorized *against*, not
                # merely that a button was pressed. This is the field-test
                # question: what did the system claim when the decision was made.
                self.recorder.record_authorization(self.engagement.readiness.state, time.time())
            return accepted, detail

    def readiness_state(self):
        with self.hub.lock:
            return self.engagement.readiness.state

    def reset(self) -> None:
        """Reset the mission so the sequence can be run again.

        Tracks and designations are cleared too, so a fresh run starts from
        UAV-001 rather than continuing to increment. The detector keeps its
        background model — the scene did not change.

        A reset also closes the current mission report and opens a new one:
        each run is a separate test, and merging two into one report loses the
        boundary that makes them comparable.
        """
        with self.hub.lock:
            self.engagement.reset()
            self.perception.reset_tracks()
        self.hub.emit(
            EventKind.INFO,
            "Mission reset. Ready for a new run.",
            code=EventCode.MISSION_RESET,
        )
        self.recorder.finish(reason="reset")
        self._begin_run()

    # ------------------------------------------------------------------
    # Input selection (API thread)
    # ------------------------------------------------------------------

    def source_status(self) -> SourceStatus:
        with self.hub.lock:
            detector = self.detector.name
            threshold = self.detector.threshold
        return self.inputs.status(detector=detector, threshold=threshold)

    def use_video_file(self, path: Path) -> str:
        return self.inputs.request_video_file(path)

    def use_camera(self, index: int) -> str:
        return self.inputs.request_camera(index)

    def use_detector(self, kind: str) -> str:
        return self.inputs.request_detector(kind)

    def set_detection_threshold(self, value: float) -> float:
        with self.hub.lock:
            applied = self.perception.set_threshold(value)
        log.info("Detection threshold set to %.2f", applied)
        return applied

    # ------------------------------------------------------------------
    # Reads (API thread)
    # ------------------------------------------------------------------

    def snapshot(self) -> TelemetryFrame | None:
        return self.hub.snapshot()

    def jpeg(self) -> bytes | None:
        return self.hub.jpeg()

    def event_log(self) -> list[MissionEvent]:
        return self.hub.event_log()

    def wait_for_frame(self, last_sequence: int, timeout: float = 1.0):
        return self.hub.wait_for_frame(last_sequence, timeout)

    # ------------------------------------------------------------------
    # Worker loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        consecutive_failures = 0

        while not self._stop.is_set():
            loop_started = time.perf_counter()

            # Apply queued input changes here, between frames — never while a
            # read() is in flight.
            self._apply_pending_input()

            try:
                frame = self.video.read()
            except Exception:  # pragma: no cover - defensive
                log.exception("Video source raised while reading")
                frame = None

            if frame is None:
                consecutive_failures += 1
                if consecutive_failures == 1:
                    self.hub.emit(
                        EventKind.WARNING,
                        f"No frame from {self.video.describe}. Attempting to recover.",
                        code=EventCode.SENSOR_LOST,
                    )
                self._publish_offline()
                # Back off so a dead source does not spin the CPU.
                time.sleep(0.2)
                continue

            if consecutive_failures:
                self.hub.emit(
                    EventKind.INFO,
                    f"Video restored from {self.video.describe}.",
                    code=EventCode.SENSOR_RESTORED,
                )
                consecutive_failures = 0

            # A rewind or reconnect breaks temporal continuity. Reset the
            # scene-dependent stages so they do not interpret the jump as
            # motion — otherwise every loop of the demo clip produces a burst
            # of false targets.
            if self.video.consume_discontinuity():
                self._reset_scene(reason="Video discontinuity")
                log.info("Video discontinuity — perception state reset")

            try:
                self._process_frame(frame)
            except Exception:  # pragma: no cover - defensive
                log.exception("Pipeline failed processing a frame")
                self.hub.emit(
                    EventKind.ERROR,
                    "Pipeline error while processing a frame.",
                    code=EventCode.ERROR,
                )

            elapsed = time.perf_counter() - loop_started
            if elapsed > 0:
                self._fps_samples.append(1.0 / elapsed)
                self._fps = sum(self._fps_samples) / len(self._fps_samples)

    def _apply_pending_input(self) -> None:
        """Apply any queued source or detector change."""
        reason = self.inputs.apply_pending_source()
        if reason is not None:
            self._reset_scene(reason=reason)
            # A new source is a new test. Close the report and open another,
            # so two clips never share one record. Note this is deliberately
            # *not* done on a video discontinuity: a looping demo clip rewinds
            # constantly, and each rewind is not a separate run.
            self.recorder.finish(reason="source changed")
            self._begin_run()

        kind, detector_reason = self.inputs.take_pending_detector(self.detector)
        if kind is None:
            return

        candidate = self.perception.build_detector(kind)
        # `build_detector` falls back to motion when YOLO's dependencies are
        # missing, so an unavailable model shows up as a name mismatch.
        if candidate.name != kind:
            self.inputs.reject_detector(kind)
            return

        with self.hub.lock:
            previous = self.perception.install_detector(candidate)
        self._reset_scene(reason=detector_reason or f"Detector changed to {kind}")
        previous.close()
        self.inputs.confirm_detector(candidate.name)

    def _reset_scene(self, *, reason: str) -> None:
        """Clear every scene-dependent stage. Used when the input changes."""
        with self.hub.lock:
            self.perception.reset()
            self.engagement.reset(reason=reason)
            self._frame_index = 0
            self._fps_samples.clear()

    def _process_frame(self, frame: np.ndarray) -> None:
        now = time.time()
        self._frame_index += 1
        height, width = frame.shape[:2]
        self._frame_size = (width, height)

        tracks = self.perception.process(frame, now)

        with self.hub.lock:
            detection = self.perception.stats(
                active_tracks=len(tracks), frames_processed=self._frame_index
            )

            # Canister health is computed before engagement, because the
            # readiness gate is a function of it — a canister that is not
            # operational must not offer an engagement.
            canister = self._canister_status(
                online=self.video.online, detection=detection, now=now
            )
            self.engagement.set_canister_health(canister.state, canister.detail)

            result = self.engagement.evaluate(
                tracks, width=width, height=height, now=now, fps=self._fps
            )
            self._record(result, detection, now)

            telemetry = TelemetryFrame(
                timestamp=now,
                system=self._system_status(
                    online=self.video.online, width=width, height=height
                ),
                mission=result.mission,
                targets=result.targets,
                detection=detection,
                canister=canister,
                readiness=result.readiness,
                launcher=result.launcher,
                tactical=build_tactical_picture(
                    result.targets, camera_hfov_deg=self.settings.camera_hfov_deg
                ),
                intercept=result.intercept,
                interceptor=result.interceptor,
                events=self.hub.drain_pending(),
            )

        # Encoded outside the lock: this costs milliseconds per frame and
        # would otherwise block every API read for its duration.
        self.hub.publish(telemetry, self._encode_jpeg(frame))

    def _publish_offline(self) -> None:
        """Publish a telemetry frame reporting the sensor as offline."""
        now = time.time()
        with self.hub.lock:
            detection = self.perception.stats(
                active_tracks=0, frames_processed=self._frame_index
            )
            telemetry = TelemetryFrame(
                timestamp=now,
                system=self._system_status(
                    online=False, width=self._frame_size[0], height=self._frame_size[1]
                ),
                mission=self.engagement.idle_status(),
                targets=[],
                detection=detection,
                canister=self._canister_status(online=False, detection=detection, now=now),
                readiness=self.engagement.readiness,
                launcher=self.engagement.launcher_status(now),
                events=self.hub.drain_pending(),
            )
        self.hub.publish(telemetry, None)

    # ------------------------------------------------------------------
    # Canister status and mission recording
    # ------------------------------------------------------------------

    def _canister_status(self, *, online: bool, detection, now: float) -> CanisterStatus:
        return self.canister.build(
            CanisterInputs(
                sensor_online=online,
                sensor_detail=self.video.describe,
                detector_ready=self.detector.ready,
                detector_name=self.detector.name,
                tracker_active_tracks=detection.active_tracks,
                fps=self._fps,
                target_fps=self.settings.target_fps,
                inference_ms=detection.latency_ms,
                launcher_state=self.engagement.launcher_status(now).state,
                launcher_simulated=self.engagement.actuator.simulated,
                interceptor_active=self.engagement.interceptor.active,
                uptime=self.canister.uptime(now),
            )
        )

    def _record(self, result, detection, now: float) -> None:
        """Feed the mission recorder. Never allowed to affect the mission."""
        state = result.mission.state
        if state is not self._recorded_state:
            self.recorder.record_transition(state, result.mission.target_id, now)
            self._recorded_state = state

        launch = self.engagement.consume_launch_record()
        if launch is not None:
            self.recorder.record_launch(*launch)

        self.recorder.record_frame_stats(
            frames=self._frame_index,
            detections_total=detection.detections_total,
            fps=self._fps,
            inference_ms=detection.latency_ms,
        )

    def _system_status(self, *, online: bool, width: int, height: int) -> SystemStatus:
        return SystemStatus(
            sensor_online=online,
            detector=self.detector.name,
            detector_ready=self.detector.ready,
            video_source=self.settings.video_source,
            fps=round(self._fps, 1) if online else 0.0,
            frame_index=self._frame_index,
            frame_width=width,
            frame_height=height,
        )

    def _encode_jpeg(self, frame: np.ndarray) -> bytes | None:
        ok, buffer = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.settings.jpeg_quality]
        )
        return buffer.tobytes() if ok else None
