"""Perception: pixels in, confirmed tracks out.

One role: run the detector and the tracker, and report how well they are
doing. This stage knows nothing about missions, targets or authorization —
it turns a frame into a list of tracks and a health readout.

The detector is swappable at runtime, so it is held as a mutable attribute
rather than captured at construction.
"""

from __future__ import annotations

import time
from collections import Counter, deque

import cv2
import numpy as np

from backend.config.settings import Settings
from backend.schemas import ClassCount, DetectionStats
from backend.vision.detector import Detection, Detector, build_detector
from backend.vision.tracker import build_tracker


class PerceptionStage:
    """Owns the detector, the tracker, and detector health statistics."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.detector: Detector = build_detector(settings)
        self.tracker = build_tracker(settings)

        # Detector health, surfaced so an operator can confirm the model is
        # working on unfamiliar footage before committing to a run.
        self._detections_total = 0
        self._detections_last = 0
        self._recent_classes: deque[str] = deque(maxlen=600)
        self._latency_samples: deque[float] = deque(maxlen=30)

        # Detection stride bookkeeping: detections from the most recent
        # inference are reused on skipped frames so the tracker still runs.
        self._stride_counter = 0
        self._last_detections: list[Detection] = []

    # ------------------------------------------------------------------
    # Frame processing
    # ------------------------------------------------------------------

    def process(self, frame: np.ndarray, now: float) -> list:
        """Detect and track on one frame. Returns the current track list."""
        detections = self._detect(frame)
        self._detections_last = len(self._last_detections)
        return self.tracker.update(detections, now)

    def _detect(self, frame: np.ndarray) -> list[Detection]:
        """Run the detector, honouring the configured detection stride.

        The detector runs every Nth frame and the tracker coasts in between
        on its velocity estimate, so the target keeps moving smoothly on
        screen while inference cost drops proportionally. This is what lets
        a neural detector keep up with a fast-moving target.
        """
        self._stride_counter += 1
        stride = max(1, self.settings.detection_stride)
        run_detector = (self._stride_counter % stride) == 0 or not self._last_detections

        if not run_detector:
            # Feeding stale boxes to the tracker again would double-count
            # hits and freeze the target in place, so skipped frames pass no
            # detections at all.
            return []

        inference_frame = self._downscale_for_inference(frame)

        started = time.perf_counter()
        detections = self.detector.detect(inference_frame)
        self._latency_samples.append((time.perf_counter() - started) * 1000.0)

        if inference_frame is not frame:
            detections = self._rescale_detections(
                detections, inference_frame.shape[1], frame.shape[1]
            )

        self._last_detections = detections
        self._detections_total += len(detections)
        self._recent_classes.extend(d.object_class for d in detections)
        return detections

    def _downscale_for_inference(self, frame: np.ndarray) -> np.ndarray:
        """Optionally shrink the frame for the detector only.

        The displayed frame keeps its resolution; only inference sees the
        smaller image. Detector cost scales with pixel count, so this is the
        cheapest available speedup when a target is still large enough to
        detect at the reduced size.
        """
        target = self.settings.inference_width
        if target <= 0 or frame.shape[1] <= target:
            return frame
        scale = target / float(frame.shape[1])
        return cv2.resize(
            frame,
            (target, max(1, int(round(frame.shape[0] * scale)))),
            interpolation=cv2.INTER_AREA,
        )

    @staticmethod
    def _rescale_detections(
        detections: list[Detection], from_width: int, to_width: int
    ) -> list[Detection]:
        """Map detections from the inference frame back to display pixels."""
        if from_width <= 0 or from_width == to_width:
            return detections
        scale = to_width / float(from_width)
        for detection in detections:
            detection.x *= scale
            detection.y *= scale
            detection.width *= scale
            detection.height *= scale
        return detections

    # ------------------------------------------------------------------
    # Detector control
    # ------------------------------------------------------------------

    def set_threshold(self, value: float) -> float:
        """Retune the live detector's confidence threshold.

        Applied without resetting perception, so the operator can watch the
        detection count respond while the same footage keeps playing.
        """
        applied = self.detector.set_threshold(value)
        # Counts gathered at the old threshold would misrepresent what the
        # new one is finding.
        self._recent_classes.clear()
        self._detections_total = 0
        return applied

    def install_detector(self, detector: Detector) -> Detector:
        """Swap in a new detector, returning the old one for the caller to close."""
        previous = self.detector
        self.detector = detector
        return previous

    def build_detector(self, kind: str) -> Detector:
        """Construct a detector of `kind` without installing it."""
        return build_detector(self.settings.model_copy(update={"detector": kind}))

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def reset_tracks(self) -> None:
        """Clear tracking state only, leaving the detector untouched.

        Used for an operator mission reset. Resetting the detector too would
        discard the motion detector's learned background model and produce a
        burst of false detections while it warms up again — on footage that
        never changed.
        """
        self.tracker.reset()
        self._stride_counter = 0
        self._last_detections = []

    def reset(self) -> None:
        """Clear all scene-dependent perception state, detector included.

        Used when the scene itself changes — a new source, a new detector, or
        a video discontinuity — where the old background model is genuinely
        stale.
        """
        self.detector.reset()
        self._detections_total = 0
        self._detections_last = 0
        self._recent_classes.clear()
        self._latency_samples.clear()
        self.reset_tracks()

    def close(self) -> None:
        self.detector.close()

    def stats(self, *, active_tracks: int, frames_processed: int) -> DetectionStats:
        """Snapshot of detector health for the telemetry frame."""
        counts = Counter(self._recent_classes)
        latency = (
            round(sum(self._latency_samples) / len(self._latency_samples), 1)
            if self._latency_samples
            else 0.0
        )
        return DetectionStats(
            detections_last_frame=self._detections_last,
            detections_total=self._detections_total,
            frames_processed=frames_processed,
            classes=[
                ClassCount(name=name, count=count) for name, count in counts.most_common(6)
            ],
            latency_ms=latency,
            active_tracks=active_tracks,
        )
