"""The perception stage.

Not detector accuracy — that is `scripts/verify_pipeline.py`'s job against
real footage. These tests cover the bookkeeping around the detector: the
stride, the inference downscale and its coordinate round-trip, and the two
different kinds of reset, all of which are invisible in a frame-by-frame
visual check but change what the operator sees.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.config.settings import Settings
from backend.pipeline.perception import PerceptionStage
from backend.vision.detector import Detection, Detector


class ScriptedDetector(Detector):
    """Returns a fixed detection list and records the frames it was given."""

    def __init__(self, detections: list[Detection] | None = None) -> None:
        self._detections = detections if detections is not None else []
        self.frames: list[np.ndarray] = []
        self.resets = 0
        self.closed = False
        self._threshold = 0.5

    @property
    def name(self) -> str:
        return "scripted"

    @property
    def ready(self) -> bool:
        return True

    def detect(self, frame: np.ndarray) -> list[Detection]:
        self.frames.append(frame)
        return [
            Detection(
                x=d.x,
                y=d.y,
                width=d.width,
                height=d.height,
                confidence=d.confidence,
                object_class=d.object_class,
                raw_class=d.raw_class,
            )
            for d in self._detections
        ]

    def reset(self) -> None:
        self.resets += 1

    def close(self) -> None:
        self.closed = True

    def set_threshold(self, value: float) -> float:
        self._threshold = value
        return value


def detection(x=10.0, y=10.0, w=20.0, h=20.0, cls="uav") -> Detection:
    return Detection(
        x=x, y=y, width=w, height=h, confidence=0.9, object_class=cls, raw_class=cls
    )


def frame(width=640, height=360) -> np.ndarray:
    return np.zeros((height, width, 3), dtype=np.uint8)


@pytest.fixture
def stage(monkeypatch):
    """A PerceptionStage whose detector is scripted rather than real."""

    def make(detections=None, **settings_overrides):
        settings = Settings(**settings_overrides)
        scripted = ScriptedDetector(detections if detections is not None else [detection()])
        monkeypatch.setattr("backend.pipeline.perception.build_detector", lambda _s: scripted)
        built = PerceptionStage(settings)
        return built, scripted

    return make


class TestDetectionStride:
    def test_runs_the_detector_on_every_frame_by_default(self, stage):
        perception, detector = stage(detection_stride=1)
        for _ in range(3):
            perception.process(frame(), now=0.0)
        assert len(detector.frames) == 3

    # The tracker coasts on velocity between inferences, which is what lets a
    # neural detector keep up with a fast target.
    def test_skips_inference_between_strides(self, stage):
        perception, detector = stage(detection_stride=3)
        for _ in range(6):
            perception.process(frame(), now=0.0)
        # Frames 3 and 6 by the stride, plus frame 1: nothing had been
        # detected yet, so the bootstrap clause forces that one to run.
        assert len(detector.frames) == 3

    def test_a_skipped_frame_passes_no_detections_to_the_tracker(self, stage):
        """Re-feeding stale boxes would double-count hits and freeze the target."""
        perception, _ = stage(detection_stride=3)
        perception.process(frame(), now=0.0)  # runs
        before = perception.stats(active_tracks=0, frames_processed=1).detections_total
        perception.process(frame(), now=0.1)  # skipped
        after = perception.stats(active_tracks=0, frames_processed=2).detections_total
        assert after == before

    # Otherwise a stride > 1 would never find the first target at all.
    def test_always_runs_while_nothing_has_been_detected_yet(self, stage):
        perception, detector = stage([], detection_stride=5)
        for _ in range(4):
            perception.process(frame(), now=0.0)
        assert len(detector.frames) == 4

    def test_treats_a_stride_below_one_as_one(self, stage):
        perception, detector = stage(detection_stride=0)
        for _ in range(3):
            perception.process(frame(), now=0.0)
        assert len(detector.frames) == 3


class TestInferenceDownscale:
    def test_shrinks_the_frame_for_the_detector_only(self, stage):
        perception, detector = stage(inference_width=320)
        original = frame(width=640, height=360)
        perception.process(original, now=0.0)

        assert detector.frames[0].shape[1] == 320
        assert original.shape[1] == 640, "the displayed frame must keep its resolution"

    def test_is_disabled_by_a_non_positive_width(self, stage):
        perception, detector = stage(inference_width=0)
        perception.process(frame(width=640), now=0.0)
        assert detector.frames[0].shape[1] == 640

    def test_never_upscales(self, stage):
        perception, detector = stage(inference_width=1280)
        perception.process(frame(width=640), now=0.0)
        assert detector.frames[0].shape[1] == 640

    # If this round trip were wrong, every box would land in the wrong place.
    def test_maps_detections_back_to_display_pixels(self, stage):
        perception, _ = stage([detection(x=10, y=20, w=30, h=40)], inference_width=320)
        tracks = perception.process(frame(width=640, height=360), now=0.0)

        assert tracks, "expected the detection to become a track"
        assert tracks[0].x == pytest.approx(20.0)
        assert tracks[0].y == pytest.approx(40.0)
        assert tracks[0].width == pytest.approx(60.0)

    def test_leaves_coordinates_alone_when_no_downscale_happened(self, stage):
        perception, _ = stage([detection(x=10, y=20)], inference_width=0)
        tracks = perception.process(frame(width=640), now=0.0)
        assert tracks[0].x == pytest.approx(10.0)


class TestThreshold:
    def test_applies_the_new_threshold_to_the_live_detector(self, stage):
        perception, detector = stage()
        assert perception.set_threshold(0.8) == 0.8
        assert detector._threshold == 0.8

    # Counts gathered at the old threshold would misrepresent the new one.
    def test_clears_counts_so_the_operator_sees_the_new_threshold_only(self, stage):
        perception, _ = stage()
        perception.process(frame(), now=0.0)
        assert perception.stats(active_tracks=0, frames_processed=1).detections_total > 0

        perception.set_threshold(0.8)
        assert perception.stats(active_tracks=0, frames_processed=1).detections_total == 0


class TestDetectorSwap:
    def test_install_returns_the_previous_detector_for_the_caller_to_close(self, stage):
        perception, original = stage()
        replacement = ScriptedDetector()

        returned = perception.install_detector(replacement)
        assert returned is original
        assert perception.detector is replacement

    def test_build_detector_does_not_install_it(self, stage, monkeypatch):
        perception, original = stage()
        built: list[str] = []
        monkeypatch.setattr(
            "backend.pipeline.perception.build_detector",
            lambda s: built.append(s.detector) or ScriptedDetector(),
        )

        perception.build_detector("motion")
        assert built == ["motion"]
        assert perception.detector is original


class TestReset:
    # Resetting the detector too would discard the motion detector's learned
    # background and produce a burst of false detections on unchanged footage.
    def test_reset_tracks_leaves_the_detector_alone(self, stage):
        perception, detector = stage()
        perception.process(frame(), now=0.0)

        perception.reset_tracks()
        assert detector.resets == 0
        assert perception.process(frame(), now=0.1) is not None

    def test_reset_tracks_clears_stride_bookkeeping(self, stage):
        perception, detector = stage(detection_stride=3)
        for _ in range(3):
            perception.process(frame(), now=0.0)
        ran_before = len(detector.frames)

        perception.reset_tracks()
        perception.process(frame(), now=0.1)
        assert len(detector.frames) == ran_before + 1

    def test_full_reset_clears_the_detector_and_the_statistics(self, stage):
        perception, detector = stage()
        perception.process(frame(), now=0.0)

        perception.reset()
        assert detector.resets == 1
        stats = perception.stats(active_tracks=0, frames_processed=0)
        assert stats.detections_total == 0
        assert stats.detections_last_frame == 0
        assert stats.classes == []
        assert stats.latency_ms == 0.0

    def test_close_closes_the_detector(self, stage):
        perception, detector = stage()
        perception.close()
        assert detector.closed is True


class TestStats:
    def test_reports_zero_latency_before_any_inference(self, stage):
        perception, _ = stage()
        assert perception.stats(active_tracks=0, frames_processed=0).latency_ms == 0.0

    def test_measures_inference_latency_once_a_frame_has_run(self, stage):
        perception, _ = stage()
        perception.process(frame(), now=0.0)
        assert perception.stats(active_tracks=0, frames_processed=1).latency_ms >= 0.0

    def test_counts_classes_seen_most_common_first(self, stage):
        perception, _ = stage(
            [detection(cls="uav"), detection(x=200, cls="uav"), detection(x=400, cls="bird")]
        )
        perception.process(frame(), now=0.0)

        stats = perception.stats(active_tracks=2, frames_processed=1)
        assert [c.name for c in stats.classes] == ["uav", "bird"]
        assert stats.classes[0].count == 2

    def test_reports_at_most_six_classes(self, stage):
        many = [detection(x=i * 40, cls=f"class{i}") for i in range(9)]
        perception, _ = stage(many)
        perception.process(frame(), now=0.0)
        assert len(perception.stats(active_tracks=0, frames_processed=1).classes) == 6

    def test_passes_through_the_caller_s_track_and_frame_counts(self, stage):
        perception, _ = stage()
        stats = perception.stats(active_tracks=3, frames_processed=42)
        assert stats.active_tracks == 3
        assert stats.frames_processed == 42
