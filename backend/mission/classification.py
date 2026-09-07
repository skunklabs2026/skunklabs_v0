"""Platform classification — FPV multirotor vs fixed-wing.

Why this exists
---------------
The two threat platforms behave nothing alike, and treating them the same
makes both the predicted trajectory and the assessed speed wrong:

  MULTIROTOR (FPV quad)   Can hover, stop, reverse and turn on the spot.
                          Slow-to-moderate, highly variable speed. A long
                          straight-line extrapolation is meaningless — it
                          may not be going that way in half a second.

  FIXED_WING (Shahed-type) Cannot hover or stop. Holds a near-constant high
                          speed on a smooth, low-curvature path. A straight
                          extrapolation is *good*, and can be trusted over a
                          longer horizon.

So the classification feeds two things: how far ahead we are willing to
predict, and — because the two airframes are an order of magnitude apart in
physical size — what absolute speed a given image-plane motion implies.

How it works
------------
Deterministic kinematics only. No model, no inference, no LLM. Four features
computed over a rolling window of observed track positions:

  straightness   net displacement / path length. ~1.0 for a fixed-wing
                 cruise, lower for a manoeuvring quad.
  speed_cv       coefficient of variation of speed. Low for fixed-wing
                 (it must keep flying), high for a quad.
  turn_rate      mean heading change, degrees per second.
  hover_fraction fraction of samples nearly stationary. A fixed-wing
                 physically cannot do this; a quad routinely does.

Each feature votes, the votes are summed, and a decision requires both a
clear margin and a run of consistent frames (hysteresis) — a classification
that flickers between airframes every frame is worse than no classification.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from backend.schemas import PlatformClass, PlatformFeatures


@dataclass(frozen=True)
class PlatformProfile:
    """What a classification implies for prediction and speed assessment."""

    label: str
    # Characteristic airframe size in metres, used to turn an apparent
    # bounding-box size into a range estimate. These are order-of-magnitude
    # figures for the class, not measurements of a specific airframe.
    characteristic_size_m: float
    # Multiplier applied to the base prediction horizon. A fixed-wing holds
    # its course, so we predict further ahead; a quad may not.
    horizon_scale: float
    # Multiplier applied to trajectory confidence, reflecting how much the
    # airframe can invalidate a straight-line extrapolation.
    confidence_scale: float
    # Plausible speed band for the class, m/s — used only to label an
    # estimate as consistent or anomalous, never to override a measurement.
    typical_speed_ms: tuple[float, float]


# Deliberately conservative, and documented as assumptions rather than facts.
PROFILES: dict[PlatformClass, PlatformProfile] = {
    PlatformClass.MULTIROTOR: PlatformProfile(
        label="FPV / multirotor",
        characteristic_size_m=0.35,
        horizon_scale=0.6,
        confidence_scale=0.75,
        typical_speed_ms=(0.0, 45.0),
    ),
    PlatformClass.FIXED_WING: PlatformProfile(
        label="Fixed-wing",
        characteristic_size_m=2.5,
        horizon_scale=1.6,
        confidence_scale=1.0,
        typical_speed_ms=(25.0, 200.0),
    ),
    PlatformClass.UNKNOWN: PlatformProfile(
        label="Unclassified",
        characteristic_size_m=1.0,
        horizon_scale=1.0,
        confidence_scale=0.85,
        typical_speed_ms=(0.0, 200.0),
    ),
}


class Vote(str, Enum):
    MULTIROTOR = "multirotor"
    FIXED_WING = "fixed_wing"
    NEUTRAL = "neutral"


@dataclass
class _Sample:
    t: float
    x: float
    y: float
    size: float  # bbox width, normalised


class PlatformClassifier:
    """Classifies a track's airframe from its observed kinematics."""

    def __init__(
        self,
        *,
        window: int = 90,
        min_samples: int = 12,
        hover_speed: float = 0.02,
        straight_threshold: float = 0.93,
        speed_cv_threshold: float = 0.35,
        turn_rate_threshold: float = 35.0,
        commit_frames: int = 8,
    ) -> None:
        self.window = window
        self.min_samples = min_samples
        self.hover_speed = hover_speed
        self.straight_threshold = straight_threshold
        self.speed_cv_threshold = speed_cv_threshold
        self.turn_rate_threshold = turn_rate_threshold
        self.commit_frames = commit_frames

        self._samples: dict[int, list[_Sample]] = {}
        # Per-track committed classification and the streak supporting it.
        self._committed: dict[int, PlatformClass] = {}
        self._streak: dict[int, tuple[PlatformClass, int]] = {}

    def reset(self) -> None:
        self._samples.clear()
        self._committed.clear()
        self._streak.clear()

    def forget(self, track_id: int) -> None:
        self._samples.pop(track_id, None)
        self._committed.pop(track_id, None)
        self._streak.pop(track_id, None)

    def observe(
        self,
        track_id: int,
        *,
        t: float,
        x: float,
        y: float,
        size: float,
    ) -> None:
        """Record one normalised observation for a track."""
        samples = self._samples.setdefault(track_id, [])
        samples.append(_Sample(t=t, x=x, y=y, size=size))
        if len(samples) > self.window:
            del samples[: len(samples) - self.window]

    def classify(self, track_id: int) -> tuple[PlatformClass, PlatformFeatures]:
        """Classify a track. Returns the committed class and its features."""
        samples = self._samples.get(track_id, [])
        features = self._features(samples)

        if len(samples) < self.min_samples:
            return PlatformClass.UNKNOWN, features

        instant = self._vote(features)
        committed = self._commit(track_id, instant)
        return committed, features

    # ------------------------------------------------------------------
    # Feature extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _smooth(samples: list[_Sample], window: int = 5) -> list[tuple[float, float, float]]:
        """Centred moving average over positions, returning (t, x, y)."""
        n = len(samples)
        if n < window:
            return [(s.t, s.x, s.y) for s in samples]

        half = window // 2
        smoothed: list[tuple[float, float, float]] = []
        for i in range(n):
            lo = max(0, i - half)
            hi = min(n, i + half + 1)
            span = samples[lo:hi]
            smoothed.append(
                (
                    samples[i].t,
                    sum(p.x for p in span) / len(span),
                    sum(p.y for p in span) / len(span),
                )
            )
        return smoothed

    def _headings(
        self,
        points: list[tuple[float, float, float]],
        *,
        stride: int = 4,
        min_step: float = 0.004,
    ) -> list[tuple[float, float]]:
        """Headings over a multi-frame baseline, as (t, degrees).

        Steps shorter than `min_step` are skipped — their direction is noise,
        and a hovering target has no meaningful heading at all.
        """
        headings: list[tuple[float, float]] = []
        for i in range(0, len(points) - stride, stride):
            t0, x0, y0 = points[i]
            t1, x1, y1 = points[i + stride]
            dx, dy = x1 - x0, y1 - y0
            if math.hypot(dx, dy) < min_step:
                continue
            headings.append((t1, math.degrees(math.atan2(dy, dx))))
        return headings

    def _features(self, samples: list[_Sample]) -> PlatformFeatures:
        if len(samples) < 3:
            return PlatformFeatures()

        # Smooth before measuring anything.
        #
        # Tracker centres jitter by a pixel or two between frames. On a short
        # per-frame step that jitter is a large fraction of the displacement,
        # so raw consecutive samples make a dead-straight run look like it is
        # turning hundreds of degrees per second, and inflate path length
        # enough to destroy the straightness metric. Both features then read
        # "multirotor" for every target. Smoothing measures the flight path
        # rather than the measurement noise.
        points = self._smooth(samples)

        speeds: list[float] = []
        path_length = 0.0

        for (t0, x0, y0), (t1, x1, y1) in zip(points, points[1:]):
            dt = t1 - t0
            if dt <= 0:
                continue
            step = math.hypot(x1 - x0, y1 - y0)
            path_length += step
            speeds.append(step / dt)

        if not speeds:
            return PlatformFeatures()

        # Headings over a multi-frame baseline, for the same reason: the
        # displacement must be large compared with the position noise before
        # its direction means anything.
        headings = self._headings(points)

        net = math.hypot(points[-1][1] - points[0][1], points[-1][2] - points[0][2])
        straightness = net / path_length if path_length > 1e-9 else 0.0

        mean_speed = sum(speeds) / len(speeds)
        if mean_speed > 1e-9:
            variance = sum((s - mean_speed) ** 2 for s in speeds) / len(speeds)
            speed_cv = math.sqrt(variance) / mean_speed
        else:
            speed_cv = 0.0

        # Mean absolute heading change per second, wrapped to [-180, 180].
        turn_rate = 0.0
        if len(headings) >= 2:
            deltas = []
            elapsed = 0.0
            for (t0, h0), (t1, h1) in zip(headings, headings[1:]):
                dt = t1 - t0
                if dt <= 0:
                    continue
                delta = (h1 - h0 + 180.0) % 360.0 - 180.0
                deltas.append(abs(delta))
                elapsed += dt
            if deltas and elapsed > 1e-6:
                turn_rate = sum(deltas) / elapsed

        hover_fraction = sum(1 for s in speeds if s < self.hover_speed) / len(speeds)

        return PlatformFeatures(
            straightness=round(straightness, 4),
            speed_cv=round(speed_cv, 4),
            turn_rate=round(turn_rate, 2),
            hover_fraction=round(hover_fraction, 4),
            mean_speed=round(mean_speed, 5),
            samples=len(samples),
        )

    # ------------------------------------------------------------------
    # Voting and hysteresis
    # ------------------------------------------------------------------

    def _vote(self, f: PlatformFeatures) -> PlatformClass:
        score = 0

        # A straight path is the strongest fixed-wing indicator.
        if f.straightness >= self.straight_threshold:
            score += 2
        elif f.straightness < 0.75:
            score -= 2

        # Steady speed suggests an airframe that must keep flying.
        if f.speed_cv <= self.speed_cv_threshold:
            score += 1
        elif f.speed_cv > self.speed_cv_threshold * 2:
            score -= 1

        # High turn rate is a rotorcraft signature.
        if f.turn_rate >= self.turn_rate_threshold:
            score -= 2
        elif f.turn_rate < self.turn_rate_threshold * 0.4:
            score += 1

        # Hovering is decisive: a fixed-wing cannot do it.
        if f.hover_fraction > 0.12:
            score -= 3

        if score >= 2:
            return PlatformClass.FIXED_WING
        if score <= -2:
            return PlatformClass.MULTIROTOR
        return PlatformClass.UNKNOWN

    def _commit(self, track_id: int, instant: PlatformClass) -> PlatformClass:
        """Require a run of consistent votes before changing the answer."""
        previous_class, count = self._streak.get(track_id, (instant, 0))
        count = count + 1 if instant is previous_class else 1
        self._streak[track_id] = (instant, count)

        if count >= self.commit_frames and instant is not PlatformClass.UNKNOWN:
            self._committed[track_id] = instant

        return self._committed.get(track_id, PlatformClass.UNKNOWN)


def profile_for(platform: PlatformClass) -> PlatformProfile:
    return PROFILES.get(platform, PROFILES[PlatformClass.UNKNOWN])


def build_platform_classifier(settings) -> PlatformClassifier:
    return PlatformClassifier(
        window=settings.platform_window,
        min_samples=settings.platform_min_samples,
        hover_speed=settings.platform_hover_speed,
        straight_threshold=settings.platform_straight_threshold,
        speed_cv_threshold=settings.platform_speed_cv_threshold,
        turn_rate_threshold=settings.platform_turn_rate_threshold,
        commit_frames=settings.platform_commit_frames,
    )
