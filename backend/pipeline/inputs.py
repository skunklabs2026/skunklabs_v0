"""Runtime input selection: which video source and which detector are live.

One role: let the operator change the input without restarting the backend,
safely. The API thread *requests* a change; the worker thread *applies* it
between frames. Swapping a `VideoCapture` underneath an in-flight `read()`
is a reliable way to crash OpenCV, so the two are kept strictly apart.

This module owns the live `VideoSource` and the record of what is currently
configured. It builds a replacement detector but does not install it — that
belongs to the perception stage, which owns detectors.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from backend.config.settings import Settings
from backend.schemas import EventCode, EventKind, SourceStatus
from backend.video.library import VideoLibrary
from backend.video.source import (
    CameraVideoSource,
    FileVideoSource,
    VideoSource,
    build_video_source,
)
from backend.vision.detector import Detector

log = logging.getLogger(__name__)

DETECTOR_KINDS = ("motion", "yolo")


class InputController:
    """Holds the live video source and applies queued input changes."""

    def __init__(
        self,
        settings: Settings,
        library: VideoLibrary,
        emit,
        lock: threading.RLock,
    ) -> None:
        self.settings = settings
        self.library = library
        self._emit = emit
        # Shares the hub's lock so a status read never observes a half-applied
        # swap.
        self._lock = lock

        self.video: VideoSource = build_video_source(settings)

        # Current configuration, mutable at runtime.
        self._source_kind = settings.video_source
        self._video_path: Path | None = (
            Path(settings.video_path) if settings.video_source == "file" else None
        )
        self._camera_index = settings.camera_index

        # Requested by the API thread, applied by the worker thread.
        self._pending_source: VideoSource | None = None
        self._pending_source_label = ""
        self._pending_detector: str | None = None

    # ------------------------------------------------------------------
    # Requests (API thread)
    # ------------------------------------------------------------------

    def request_video_file(self, path: Path) -> str:
        """Queue a switch to a video file. Returns an operator-readable note."""
        source = FileVideoSource(
            path,
            target_fps=self.settings.target_fps,
            frame_width=self.settings.frame_width,
            loop=self.settings.loop_video,
        )
        with self._lock:
            self._pending_source = source
            self._pending_source_label = f"file:{path.name}"
            self._source_kind = "file"
            self._video_path = path
        return f"Loading {path.name}."

    def request_camera(self, index: int) -> str:
        source = CameraVideoSource(index, frame_width=self.settings.frame_width)
        with self._lock:
            self._pending_source = source
            self._pending_source_label = f"camera:{index}"
            self._source_kind = "camera"
            self._video_path = None
            self._camera_index = index
        return f"Switching to camera {index}."

    def request_detector(self, kind: str) -> str:
        """Queue a detector swap, applied by the worker thread."""
        if kind not in DETECTOR_KINDS:
            raise ValueError(f"Unknown detector '{kind}'. Use 'motion' or 'yolo'.")
        with self._lock:
            self._pending_detector = kind
        return f"Switching detector to {kind}."

    # ------------------------------------------------------------------
    # Application (worker thread)
    # ------------------------------------------------------------------

    def apply_pending_source(self) -> str | None:
        """Swap in a queued video source.

        Returns a reason string if the source changed, else None. The old
        source is retained on failure — a bad path must never leave the demo
        with no video at all.
        """
        with self._lock:
            source = self._pending_source
            label = self._pending_source_label
            self._pending_source = None
        if source is None:
            return None

        previous = self.video
        if not source.open():
            self._emit(
                EventKind.ERROR,
                f"Could not open {label}. Keeping {previous.describe}.",
                code=EventCode.ERROR,
            )
            log.error("Failed to open %s; retaining previous source", label)
            with self._lock:
                # Keep the reported configuration honest about what is live.
                self._source_kind = (
                    "file" if isinstance(previous, FileVideoSource) else "camera"
                )
            return None

        previous.release()
        with self._lock:
            self.video = source
        self._emit(
            EventKind.INFO,
            f"Video source: {source.describe}.",
            code=EventCode.SOURCE_CHANGED,
        )
        log.info("Video source switched to %s", source.describe)
        return f"Source changed to {label}"

    def take_pending_detector(self, current: Detector) -> tuple[str | None, str | None]:
        """Return the detector kind to install, if a valid swap is queued.

        Returns (kind, reason). `kind` is None when there is nothing to do or
        the requested detector is unavailable.
        """
        with self._lock:
            kind = self._pending_detector
            self._pending_detector = None

        if kind is None or kind == current.name:
            return None, None
        return kind, f"Detector changed to {kind}"

    def reject_detector(self, kind: str) -> None:
        """Report that a requested detector could not be constructed."""
        self._emit(
            EventKind.ERROR,
            f"{kind.upper()} unavailable (install requirements-yolo.txt). "
            "Keeping motion detector.",
            code=EventCode.ERROR,
        )

    def confirm_detector(self, name: str) -> None:
        self._emit(
            EventKind.INFO, f"Detector: {name}.", code=EventCode.SOURCE_CHANGED
        )
        log.info("Detector switched to %s", name)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self, *, detector: str, threshold: float) -> SourceStatus:
        """Current input configuration plus the available library."""
        with self._lock:
            active = self._video_path if self._source_kind == "file" else None
            kind = self._source_kind
            camera_index = self._camera_index
        return SourceStatus(
            video_source=kind,
            active_video=str(active) if active else None,
            camera_index=camera_index,
            detector=detector,
            detection_threshold=round(threshold, 3),
            detectors_available=list(DETECTOR_KINDS),
            videos=self.library.list_videos(active),
        )
