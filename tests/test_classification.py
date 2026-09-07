"""Platform classification and speed assessment."""

from __future__ import annotations

import math

import pytest

from backend.mission.classification import (
    PlatformClassifier,
    profile_for,
)
from backend.mission.speed import SpeedEstimator
from backend.schemas import PlatformClass

DT = 0.04  # 25 fps


def feed(classifier: PlatformClassifier, points, *, track_id: int = 1, size: float = 0.05):
    """Feed a list of (x, y) samples at a fixed frame interval.

    Classifies after every observation, exactly as the pipeline does — the
    commit hysteresis counts consecutive *classify* calls, so feeding in bulk
    and classifying once would never commit.
    """
    result = classifier.classify(track_id)
    for i, (x, y) in enumerate(points):
        classifier.observe(track_id, t=i * DT, x=x, y=y, size=size)
        result = classifier.classify(track_id)
    return result


def straight_flight(n: int = 60, speed: float = 0.012):
    """A fixed-wing cruise: fast, dead straight, constant speed."""
    return [(0.05 + i * speed, 0.4 + i * speed * 0.15) for i in range(n)]


def hovering_quad(n: int = 60):
    """A multirotor holding station.

    Drift per frame is well under `platform_hover_speed` x DT, so these
    samples genuinely register as hovering rather than merely slow.
    """
    return [
        (0.5 + 0.0002 * math.sin(i * 0.7), 0.5 + 0.0002 * math.cos(i * 0.9)) for i in range(n)
    ]


def darting_quad(n: int = 80):
    """A multirotor changing direction sharply and varying speed."""
    points = []
    x, y = 0.3, 0.5
    for i in range(n):
        leg = i // 10
        if leg % 4 == 0:
            x += 0.012
        elif leg % 4 == 1:
            y += 0.011
        elif leg % 4 == 2:
            x -= 0.013
        else:
            y -= 0.010
        points.append((x, y))
    return points


class TestClassifier:
    def test_unknown_before_enough_samples(self):
        classifier = PlatformClassifier()
        platform, features = feed(classifier, straight_flight(n=5))
        assert platform is PlatformClass.UNKNOWN
        assert features.samples <= 5

    def test_identifies_fixed_wing(self):
        classifier = PlatformClassifier()
        platform, features = feed(classifier, straight_flight())
        assert platform is PlatformClass.FIXED_WING
        assert features.straightness > 0.95
        assert features.hover_fraction == 0.0

    def test_identifies_hovering_multirotor(self):
        """Hovering is decisive — a fixed-wing physically cannot."""
        classifier = PlatformClassifier()
        platform, features = feed(classifier, hovering_quad())
        assert platform is PlatformClass.MULTIROTOR
        assert features.hover_fraction > 0.1

    def test_identifies_darting_multirotor(self):
        classifier = PlatformClassifier()
        platform, features = feed(classifier, darting_quad())
        assert platform is PlatformClass.MULTIROTOR
        assert features.turn_rate > 0

    def test_straightness_separates_the_classes(self):
        straight = PlatformClassifier()
        feed(straight, straight_flight())
        darting = PlatformClassifier()
        feed(darting, darting_quad())

        assert straight.classify(1)[1].straightness > darting.classify(1)[1].straightness

    def test_requires_consistent_votes_before_committing(self):
        """One frame of evidence must not flip the classification."""
        classifier = PlatformClassifier(commit_frames=8, min_samples=12)
        # Exactly at min_samples: not enough consecutive votes yet.
        platform, _ = feed(classifier, straight_flight(n=13))
        assert platform is PlatformClass.UNKNOWN

    def test_classification_is_sticky(self):
        """Once committed, a couple of ambiguous frames do not undo it."""
        classifier = PlatformClassifier()
        platform, _ = feed(classifier, straight_flight())
        assert platform is PlatformClass.FIXED_WING

        # A brief wobble arrives; the committed answer holds.
        for i in range(3):
            classifier.observe(1, t=100 + i * DT, x=0.9, y=0.9, size=0.05)
        assert classifier.classify(1)[0] is PlatformClass.FIXED_WING

    def test_tracks_are_independent(self):
        classifier = PlatformClassifier()
        feed(classifier, straight_flight(), track_id=1)
        feed(classifier, hovering_quad(), track_id=2)
        assert classifier.classify(1)[0] is PlatformClass.FIXED_WING
        assert classifier.classify(2)[0] is PlatformClass.MULTIROTOR

    def test_reset_clears_everything(self):
        classifier = PlatformClassifier()
        feed(classifier, straight_flight())
        classifier.reset()
        assert classifier.classify(1)[0] is PlatformClass.UNKNOWN

    def test_is_deterministic(self):
        results = set()
        for _ in range(5):
            classifier = PlatformClassifier()
            platform, features = feed(classifier, straight_flight())
            results.add((platform, features.straightness, features.turn_rate))
        assert len(results) == 1


class TestNoiseRobustness:
    """Regression: tracker jitter must not masquerade as manoeuvring.

    Observed on a real clip — a dead-straight fixed-wing run was classified
    MULTIROTOR because heading was computed between consecutive noisy
    samples. On a short per-frame step, a pixel of jitter is a large angle,
    so the measured turn rate was hundreds of deg/s and straightness was
    destroyed by the inflated path length.
    """

    @staticmethod
    def jittered(points, amplitude: float = 0.0025, seed: int = 3):
        import random

        rng = random.Random(seed)
        return [
            (x + rng.uniform(-amplitude, amplitude), y + rng.uniform(-amplitude, amplitude))
            for x, y in points
        ]

    def test_straight_run_survives_jitter(self):
        classifier = PlatformClassifier()
        platform, features = feed(classifier, self.jittered(straight_flight()))
        assert platform is PlatformClass.FIXED_WING
        assert features.turn_rate < 90, "jitter is being read as turning"
        assert features.straightness > 0.9

    def test_jitter_does_not_inflate_turn_rate(self):
        clean = PlatformClassifier()
        feed(clean, straight_flight())
        noisy = PlatformClassifier()
        feed(noisy, self.jittered(straight_flight()))

        # Smoothing should keep the two within the same order of magnitude.
        assert noisy.classify(1)[1].turn_rate < clean.classify(1)[1].turn_rate + 90

    def test_genuine_manoeuvring_still_detected(self):
        """Smoothing must not erase real turns along with the noise."""
        classifier = PlatformClassifier()
        platform, _ = feed(classifier, self.jittered(darting_quad()))
        assert platform is PlatformClass.MULTIROTOR


class TestProfiles:
    def test_fixed_wing_predicts_further_than_multirotor(self):
        """The whole point: course-holding airframes get a longer horizon."""
        fixed = profile_for(PlatformClass.FIXED_WING)
        multi = profile_for(PlatformClass.MULTIROTOR)
        assert fixed.horizon_scale > multi.horizon_scale
        assert fixed.confidence_scale >= multi.confidence_scale

    def test_fixed_wing_is_assumed_larger(self):
        """Size drives the range inference, and so the speed estimate."""
        assert (
            profile_for(PlatformClass.FIXED_WING).characteristic_size_m
            > profile_for(PlatformClass.MULTIROTOR).characteristic_size_m
        )

    def test_unknown_has_neutral_scaling(self):
        assert profile_for(PlatformClass.UNKNOWN).horizon_scale == 1.0


class TestSpeedEstimator:
    def test_unavailable_without_fov(self):
        """No field of view means no honest absolute speed."""
        estimate = SpeedEstimator().estimate(
            image_speed=0.2,
            bbox_width=0.05,
            platform=PlatformClass.FIXED_WING,
            profile=profile_for(PlatformClass.FIXED_WING),
        )
        assert estimate.available is False
        assert "field of view" in estimate.detail
        assert estimate.image_speed == 0.2

    def test_unavailable_while_unclassified(self):
        estimator = SpeedEstimator(camera_hfov_deg=60, enabled=True)
        estimate = estimator.estimate(
            image_speed=0.2,
            bbox_width=0.05,
            platform=PlatformClass.UNKNOWN,
            profile=profile_for(PlatformClass.UNKNOWN),
        )
        assert estimate.available is False

    def test_produces_a_speed_with_fov(self):
        estimator = SpeedEstimator(camera_hfov_deg=60, enabled=True)
        estimate = estimator.estimate(
            image_speed=0.2,
            bbox_width=0.05,
            platform=PlatformClass.FIXED_WING,
            profile=profile_for(PlatformClass.FIXED_WING),
        )
        assert estimate.available
        assert estimate.range_m > 0
        assert estimate.speed_ms > 0
        # Both figures are rounded to 0.1, so allow one rounding step.
        assert estimate.speed_kmh == pytest.approx(estimate.speed_ms * 3.6, abs=0.06)

    def test_platform_changes_the_answer(self):
        """Same pixels, different airframe, very different speed.

        This is the reason classification has to come first.
        """
        estimator = SpeedEstimator(camera_hfov_deg=60, enabled=True)
        common = {"image_speed": 0.2, "bbox_width": 0.05}

        quad = estimator.estimate(
            **common,
            platform=PlatformClass.MULTIROTOR,
            profile=profile_for(PlatformClass.MULTIROTOR),
        )
        wing = estimator.estimate(
            **common,
            platform=PlatformClass.FIXED_WING,
            profile=profile_for(PlatformClass.FIXED_WING),
        )

        ratio = wing.speed_ms / quad.speed_ms
        expected = (
            profile_for(PlatformClass.FIXED_WING).characteristic_size_m
            / profile_for(PlatformClass.MULTIROTOR).characteristic_size_m
        )
        # Rounded to 0.1 m/s on the way out, so allow a little slack.
        assert ratio == pytest.approx(expected, rel=0.05)

    def test_smaller_apparent_size_means_further_and_faster(self):
        estimator = SpeedEstimator(camera_hfov_deg=60, enabled=True)
        near = estimator.estimate(
            image_speed=0.2,
            bbox_width=0.10,
            platform=PlatformClass.FIXED_WING,
            profile=profile_for(PlatformClass.FIXED_WING),
        )
        far = estimator.estimate(
            image_speed=0.2,
            bbox_width=0.02,
            platform=PlatformClass.FIXED_WING,
            profile=profile_for(PlatformClass.FIXED_WING),
        )
        assert far.range_m > near.range_m
        assert far.speed_ms > near.speed_ms

    def test_flags_implausible_speed(self):
        """An estimate outside the class's envelope says so."""
        estimator = SpeedEstimator(camera_hfov_deg=60, enabled=True)
        estimate = estimator.estimate(
            image_speed=0.0001,
            bbox_width=0.5,
            platform=PlatformClass.FIXED_WING,
            profile=profile_for(PlatformClass.FIXED_WING),
        )
        assert estimate.plausible is False
        assert "typical" in estimate.detail

    def test_states_its_assumptions(self):
        estimator = SpeedEstimator(camera_hfov_deg=60, enabled=True)
        estimate = estimator.estimate(
            image_speed=0.2,
            bbox_width=0.05,
            platform=PlatformClass.MULTIROTOR,
            profile=profile_for(PlatformClass.MULTIROTOR),
        )
        assert "Assumes" in estimate.detail
        assert "Cross-range only" in estimate.detail


class TestAgainstRealClips:
    """End-to-end: the two demo clips must classify as their own airframe.

    This runs the real detector, tracker and classifier over the generated
    clips — the check that catches feature-extraction regressions which unit
    tests on synthetic point lists would miss.
    """

    @staticmethod
    def classify_clip(name: str) -> dict[str, int]:
        import time
        from collections import Counter
        from pathlib import Path

        from backend.config.settings import get_settings
        from backend.mission.classification import build_platform_classifier
        from backend.targets.target_manager import TargetManager
        from backend.video.source import FileVideoSource
        from backend.vision.detector import build_detector
        from backend.vision.tracker import build_tracker

        clip = Path(__file__).resolve().parents[1] / "assets" / "videos" / name
        if not clip.exists():
            pytest.skip(f"{name} not generated; run scripts/make_demo_video.py")

        settings = get_settings()
        video = FileVideoSource(
            clip, target_fps=0, frame_width=settings.frame_width, loop=False
        )
        detector = build_detector(settings)
        tracker = build_tracker(settings)
        targets = TargetManager()
        classifier = build_platform_classifier(settings)

        assert video.open()
        now, dt, frames = time.time(), 1 / 25, 0
        seen: list[str] = []

        while frames < 900:
            frame = video.read()
            if frame is None:
                break
            frames += 1
            now += dt
            height, width = frame.shape[:2]
            tracks = tracker.update(detector.detect(frame), now)
            for track in tracks:
                if track.confirmed:
                    cx, cy = track.center
                    classifier.observe(
                        track.track_id,
                        t=now,
                        x=cx / width,
                        y=cy / height,
                        size=track.width / width,
                    )
            primary = targets.select_primary(tracks)
            if primary is not None:
                seen.append(classifier.classify(primary.track_id)[0].value)

        video.release()
        counts = Counter(seen)
        total = sum(counts.values()) or 1
        return {k: v * 100 // total for k, v in counts.items()}

    def test_fixed_wing_clip(self):
        share = self.classify_clip("demo_fixed_wing.mp4")
        assert share.get("FIXED_WING", 0) > 70, share

    def test_multirotor_clip(self):
        share = self.classify_clip("demo_multirotor.mp4")
        assert share.get("MULTIROTOR", 0) > 70, share
