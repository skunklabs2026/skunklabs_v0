"""Video ingestion.

Exposes one interface, `VideoSource`, so the rest of the pipeline never knows
whether frames come from a recorded clip, a webcam, or (later) an external
sensor. Both implementations fail soft: a read error is reported through
`online`, never raised into the pipeline loop.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)


class VideoSource(ABC):
    """A source of frames.

    Implementations must be safe to `read()` even after a failure - they
    should attempt recovery and report status rather than throwing.
    """

    @abstractmethod
    def open(self) -> bool:
        """Acquire the underlying device/file. Returns True on success."""

    @abstractmethod
    def read(self) -> np.ndarray | None:
        """Return the next BGR frame, or None if one is not available."""

    @abstractmethod
    def release(self) -> None:
        """Release the underlying resource."""

    @property
    @abstractmethod
    def online(self) -> bool:
        """Whether the source is currently delivering frames."""

    def consume_discontinuity(self) -> bool:
        """True once after the frame sequence jumps (a rewind, a reconnect).

        A discontinuity means the next frame has no temporal relationship to
        the previous one, so any stateful downstream component - a background
        model, a tracker - must be reset rather than fed a scene cut.
        Defaults to False for sources that are always continuous.
        """
        return False

    @property
    def describe(self) -> str:
        return self.__class__.__name__


def _resize_to_width(frame: np.ndarray, width: int) -> np.ndarray:
    """Scale a frame to `width`, preserving aspect ratio. No upscaling."""
    h, w = frame.shape[:2]
    if w <= width:
        return frame
    scale = width / float(w)
    return cv2.resize(frame, (width, int(round(h * scale))), interpolation=cv2.INTER_AREA)


class FileVideoSource(VideoSource):
    """Replays a local video file at a controlled rate.

    This is the demo default: a recorded clip removes environmental
    variability, which is what makes the demo repeatable.
    """

    def __init__(
        self,
        path: Path | str,
        *,
        target_fps: float = 25.0,
        frame_width: int = 960,
        loop: bool = True,
    ) -> None:
        self.path = Path(path)
        self.target_fps = target_fps
        self.frame_width = frame_width
        self.loop = loop
        self._cap: cv2.VideoCapture | None = None
        self._online = False
        self._frame_interval = 1.0 / target_fps if target_fps > 0 else 0.0
        self._next_frame_at = 0.0
        self._discontinuity = False

    def open(self) -> bool:
        if not self.path.exists():
            log.error("Video file not found: %s", self.path)
            self._online = False
            return False
        cap = cv2.VideoCapture(str(self.path))
        if not cap.isOpened():
            log.error("Could not open video file: %s", self.path)
            self._online = False
            return False
        self._cap = cap
        self._online = True
        self._next_frame_at = time.monotonic()
        log.info(
            "Video file opened: %s (%dx%d @ %.1f fps source)",
            self.path.name,
            int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            cap.get(cv2.CAP_PROP_FPS) or 0.0,
        )
        return True

    def read(self) -> np.ndarray | None:
        if self._cap is None and not self.open():
            return None
        assert self._cap is not None

        # Pace playback to target_fps so a 30 fps clip does not race through
        # the pipeline faster than the operator can watch it.
        if self._frame_interval:
            now = time.monotonic()
            sleep_for = self._next_frame_at - now
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._next_frame_at = max(now, self._next_frame_at) + self._frame_interval

        ok, frame = self._cap.read()
        if not ok:
            if self.loop:
                # Rewind and continue, so the demo can run back-to-back.
                # The jump back to frame 0 is a scene cut: flag it so the
                # detector's background model and the tracker are reset.
                # Without this, the background subtractor reads the entire
                # rewound frame as foreground and floods the operator screen
                # with false targets at every loop.
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self._discontinuity = True
                ok, frame = self._cap.read()
            if not ok:
                log.warning("End of video: %s", self.path.name)
                self._online = False
                return None
        self._online = True
        return _resize_to_width(frame, self.frame_width)

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._online = False

    @property
    def online(self) -> bool:
        return self._online

    def consume_discontinuity(self) -> bool:
        if self._discontinuity:
            self._discontinuity = False
            return True
        return False

    @property
    def describe(self) -> str:
        return f"file:{self.path.name}"


class CameraVideoSource(VideoSource):
    """Reads from a USB / built-in camera, with automatic reconnection."""

    # Seconds to wait between reconnection attempts after the camera drops.
    RECONNECT_INTERVAL = 2.0

    def __init__(
        self,
        index: int = 0,
        *,
        frame_width: int = 960,
    ) -> None:
        self.index = index
        self.frame_width = frame_width
        self._cap: cv2.VideoCapture | None = None
        self._online = False
        self._next_retry_at = 0.0
        self._discontinuity = False

    def open(self) -> bool:
        cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            log.error("Could not open camera index %d", self.index)
            cap.release()
            self._online = False
            self._next_retry_at = time.monotonic() + self.RECONNECT_INTERVAL
            return False
        self._cap = cap
        self._online = True
        log.info("Camera %d opened", self.index)
        return True

    def read(self) -> np.ndarray | None:
        if self._cap is None:
            # Rate-limit reconnection so a missing camera does not spin the
            # pipeline loop at full speed.
            if time.monotonic() < self._next_retry_at:
                return None
            if not self.open():
                return None
        assert self._cap is not None

        ok, frame = self._cap.read()
        if not ok:
            log.warning("Camera %d read failed; will attempt reconnect", self.index)
            self.release()
            # Frames after a reconnect have no relationship to those before.
            self._discontinuity = True
            self._next_retry_at = time.monotonic() + self.RECONNECT_INTERVAL
            return None
        self._online = True
        return _resize_to_width(frame, self.frame_width)

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._online = False

    @property
    def online(self) -> bool:
        return self._online

    def consume_discontinuity(self) -> bool:
        if self._discontinuity:
            self._discontinuity = False
            return True
        return False

    @property
    def describe(self) -> str:
        return f"camera:{self.index}"


def build_video_source(settings) -> VideoSource:
    """Construct the video source named by configuration."""
    if settings.video_source == "camera":
        return CameraVideoSource(settings.camera_index, frame_width=settings.frame_width)
    return FileVideoSource(
        settings.video_path,
        target_fps=settings.target_fps,
        frame_width=settings.frame_width,
        loop=settings.loop_video,
    )
