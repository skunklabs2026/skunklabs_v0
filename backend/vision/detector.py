"""Object detection.

`Detector` is the seam between perception and everything downstream. The
tracker, target manager, rule engine and state machine only ever see
`Detection` objects — they contain no model-specific concepts, so swapping
YOLO for anything else touches this file alone.

Two implementations ship with V0:

  MotionDetector  Background subtraction. No model weights, no torch, no
                  download. An airborne object against sky is close to the
                  ideal case for it, which makes it the most *repeatable*
                  choice for the demo — the V0 priority.

  YoloDetector    Ultralytics YOLO26n. Higher-fidelity classification, at
                  the cost of a large dependency. Optional.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

import cv2
import numpy as np

log = logging.getLogger(__name__)


@dataclass(slots=True)
class Detection:
    """One candidate object in one frame, in *pixel* coordinates."""

    x: float
    y: float
    width: float
    height: float
    confidence: float
    object_class: str
    raw_class: str = ""  # the detector's own label, before UAV mapping

    @property
    def xyxy(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)

    @property
    def area(self) -> float:
        return self.width * self.height


class Detector(ABC):
    """Detects objects of interest in a frame."""

    @abstractmethod
    def detect(self, frame: np.ndarray) -> list[Detection]:
        """Return detections for one BGR frame. Must never raise."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier surfaced in telemetry, e.g. "motion"."""

    @property
    def ready(self) -> bool:
        """Whether the detector is loaded and producing results."""
        return True

    def reset(self) -> None:
        """Discard any temporal state after a scene discontinuity.

        Stateless detectors need do nothing; detectors that model the scene
        over time must start again. Optional.
        """

    @property
    def threshold(self) -> float:
        """Current confidence threshold."""
        return getattr(self, "_threshold", 0.0)

    def set_threshold(self, value: float) -> float:
        """Adjust the confidence threshold at runtime.

        Exposed because the right threshold is a property of the *footage*,
        not of the code: a small, distant drone against overcast sky scores
        far lower than a close subject. Being able to tune this while
        watching the detection count is the difference between "the model
        does not work on my video" and "the threshold was too high".
        """
        self._threshold = max(0.0, min(1.0, float(value)))
        return self._threshold

    def close(self) -> None:  # pragma: no cover - trivial default
        """Release any resources. Optional."""


class MotionDetector(Detector):
    """Detects moving objects via MOG2 background subtraction.

    The background model adapts to a static or slowly-panning scene, so a
    drone crossing the frame stands out as foreground. Contours are filtered
    by area to reject both sensor noise (too small) and global lighting or
    camera-shake changes (too large).

    Confidence is synthesised from how solidly the contour fills its bounding
    box and how far it exceeds the noise floor. It is a heuristic quality
    score, not a class probability — but it behaves monotonically, which is
    all the downstream rule engine needs.
    """

    def __init__(
        self,
        *,
        min_area_frac: float = 0.00035,
        max_area_frac: float = 0.08,
        history: int = 240,
        var_threshold: float = 40.0,
        warmup_frames: int = 12,
        threshold: float = 0.55,
        object_class: str = "uav",
    ) -> None:
        self.min_area_frac = min_area_frac
        self.max_area_frac = max_area_frac
        self.warmup_frames = warmup_frames
        self._threshold = threshold
        self.object_class = object_class
        self._history = history
        self._var_threshold = var_threshold
        self._frames_seen = 0
        self._subtractor = self._new_subtractor()
        # A small kernel closes speckle gaps without merging distinct objects.
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    def _new_subtractor(self):
        return cv2.createBackgroundSubtractorMOG2(
            history=self._history,
            varThreshold=self._var_threshold,
            detectShadows=False,
        )

    def reset(self) -> None:
        """Rebuild the background model from scratch.

        Called on a scene cut (a looped clip rewinding, a camera reconnect).
        Adapting the existing model would take hundreds of frames, during
        which the whole frame reads as foreground and the operator sees a
        screen full of false targets.
        """
        self._subtractor = self._new_subtractor()
        self._frames_seen = 0

    @property
    def name(self) -> str:
        return "motion"

    @property
    def ready(self) -> bool:
        return self._frames_seen >= self.warmup_frames

    def detect(self, frame: np.ndarray) -> list[Detection]:
        try:
            return self._detect(frame)
        except Exception:  # pragma: no cover - defensive: never kill the loop
            log.exception("MotionDetector failed on a frame; returning no detections")
            return []

    def _detect(self, frame: np.ndarray) -> list[Detection]:
        self._frames_seen += 1
        height, width = frame.shape[:2]
        frame_area = float(height * width)

        # Blur first: suppresses per-pixel sensor noise that would otherwise
        # become hundreds of tiny contours.
        blurred = cv2.GaussianBlur(frame, (5, 5), 0)
        mask = self._subtractor.apply(blurred)

        # Let the background model settle before trusting anything — the
        # first frames register the entire scene as foreground.
        if self._frames_seen < self.warmup_frames:
            return []

        _, mask = cv2.threshold(mask, 200, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self._kernel, iterations=2)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        min_area = self.min_area_frac * frame_area
        max_area = self.max_area_frac * frame_area

        detections: list[Detection] = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area or area > max_area:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            if w == 0 or h == 0:
                continue

            # Extent: how much of the bounding box the contour actually fills.
            # A compact object (drone) scores high; a smear of noise or a
            # lighting gradient scores low.
            extent = area / float(w * h)
            # Size margin: how far above the noise floor this contour is.
            size_margin = min(1.0, area / (min_area * 6.0))
            confidence = float(np.clip(0.45 + 0.4 * extent + 0.25 * size_margin, 0.0, 0.99))

            if confidence < self.threshold:
                continue

            detections.append(
                Detection(
                    x=float(x),
                    y=float(y),
                    width=float(w),
                    height=float(h),
                    confidence=confidence,
                    object_class=self.object_class,
                    raw_class="motion",
                )
            )

        # Strongest first, so a single-target demo picks the obvious object.
        detections.sort(key=lambda d: d.confidence * d.area, reverse=True)
        return detections


class YoloDetector(Detector):
    """Ultralytics YOLO detector (YOLO26n baseline).

    COCO-pretrained models have no `drone` class, so detections whose label
    is in `uav_class_names` are relabelled to "uav". Fine-tuning on real
    demo footage is the correct long-term fix and is out of V0 scope.

    Import of `ultralytics` is deliberately deferred to construction time so
    that the demo runs with only the core requirements installed.
    """

    def __init__(
        self,
        model_path: str = "yolo26n.pt",
        *,
        threshold: float = 0.55,
        device: str = "auto",
        uav_class_names: tuple[str, ...] = ("airplane", "bird", "kite", "frisbee"),
    ) -> None:
        self.model_path = model_path
        self._threshold = threshold
        self.uav_class_names = {c.lower() for c in uav_class_names}
        self._model = None
        self._ready = False
        self.device = self._resolve_device(device)
        self._load()

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device != "auto":
            return device
        try:
            import torch

            # MPS is the Apple Silicon GPU path. Fall back to CPU, which is
            # portable and still real-time for the nano model.
            if torch.backends.mps.is_available():
                return "mps"
        except Exception:
            pass
        return "cpu"

    def _load(self) -> None:
        try:
            from ultralytics import YOLO

            self._model = YOLO(self.model_path)
            self._ready = True
            log.info("YOLO detector loaded: %s on %s", self.model_path, self.device)
        except Exception as exc:
            # A missing model or missing torch must not prevent the server
            # from starting — the caller falls back to the motion detector.
            log.error("Could not load YOLO model %s: %s", self.model_path, exc)
            self._model = None
            self._ready = False

    @property
    def name(self) -> str:
        return "yolo"

    @property
    def ready(self) -> bool:
        return self._ready

    def detect(self, frame: np.ndarray) -> list[Detection]:
        if self._model is None:
            return []
        try:
            results = self._model.predict(
                frame,
                conf=self.threshold,
                device=self.device,
                verbose=False,
            )
        except Exception:  # pragma: no cover - defensive
            log.exception("YOLO inference failed on a frame")
            return []

        detections: list[Detection] = []
        for result in results:
            names = result.names
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
                confidence = float(box.conf[0])
                raw_class = str(names.get(int(box.cls[0]), "object")).lower()
                object_class = "uav" if raw_class in self.uav_class_names else raw_class
                detections.append(
                    Detection(
                        x=x1,
                        y=y1,
                        width=x2 - x1,
                        height=y2 - y1,
                        confidence=confidence,
                        object_class=object_class,
                        raw_class=raw_class,
                    )
                )
        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections


def build_detector(settings) -> Detector:
    """Construct the configured detector, falling back to motion on failure.

    The fallback matters: a demo must degrade to a working state rather than
    to a blank screen if a model file is missing.
    """
    if settings.detector == "yolo":
        detector = YoloDetector(
            settings.model_path,
            threshold=settings.yolo_detection_threshold,
            device=settings.device,
            uav_class_names=settings.uav_class_names,
        )
        if detector.ready:
            return detector
        log.warning("YOLO unavailable — falling back to the motion detector")

    return MotionDetector(
        min_area_frac=settings.motion_min_area_frac,
        max_area_frac=settings.motion_max_area_frac,
        history=settings.motion_history,
        var_threshold=settings.motion_var_threshold,
        warmup_frames=settings.motion_warmup_frames,
        threshold=settings.detection_threshold,
    )
