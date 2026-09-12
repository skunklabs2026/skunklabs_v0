"""Absolute speed assessment.

A single uncalibrated camera cannot measure speed. What it *can* do is
measure angular rate, and angular rate becomes a speed once you know the
range. Range, in turn, follows from how large the target appears - but only
if you assume how large it actually is.

That assumption is exactly what the platform classification supplies:

    an FPV quad  (~0.35 m) subtending 20 px is close and slow
    a fixed-wing (~2.5 m)  subtending 20 px is far away and fast

Same pixels, ~7x the range, ~7x the speed. Getting the airframe wrong makes
the speed wrong by that factor, which is why classification comes first.

Every number here is an inference from stated assumptions, and the estimate
reports those assumptions alongside the value. It is not a measurement, and
the UI labels it as an estimate.

Geometry
--------
    angular size  θ = 2 · atan( (bbox_px / frame_px) · tan(HFOV/2) )
    range         R = size_m / (2 · tan(θ/2))
    angular rate  ω = image_speed · HFOV          (frame widths/s → rad/s)
    cross speed   v = R · ω

Cross-range only: motion toward or away from the camera is invisible to this,
so the result is a lower bound on true speed.
"""

from __future__ import annotations

import math

from backend.mission.classification import PlatformProfile
from backend.schemas import PlatformClass, SpeedEstimate


class SpeedEstimator:
    """Infers absolute speed from apparent size and image-plane motion."""

    def __init__(
        self,
        *,
        camera_hfov_deg: float = 0.0,
        enabled: bool = False,
    ) -> None:
        self.camera_hfov_deg = camera_hfov_deg
        # Disabled unless a field of view is configured: a fabricated m/s
        # figure is worse than an honest "not available".
        self.enabled = enabled and camera_hfov_deg > 0.0

    def estimate(
        self,
        *,
        image_speed: float,
        bbox_width: float,
        platform: PlatformClass,
        profile: PlatformProfile,
    ) -> SpeedEstimate:
        """Assess speed for one target.

        `image_speed` is in normalised frame widths per second; `bbox_width`
        is the normalised apparent width.
        """
        base = SpeedEstimate(
            available=False,
            image_speed=round(image_speed, 4),
            assumed_size_m=profile.characteristic_size_m,
        )

        if not self.enabled:
            base.detail = (
                "Absolute speed needs the camera field of view (set SKUNK_CAMERA_HFOV_DEG)."
            )
            return base

        if bbox_width <= 1e-6:
            base.detail = "Target too small to estimate range."
            return base

        if platform is PlatformClass.UNKNOWN:
            base.detail = "Awaiting platform classification."
            return base

        hfov = math.radians(self.camera_hfov_deg)
        # Apparent angular size of the target.
        angular_size = 2.0 * math.atan(bbox_width * math.tan(hfov / 2.0))
        if angular_size <= 1e-9:
            base.detail = "Target too small to estimate range."
            return base

        range_m = profile.characteristic_size_m / (2.0 * math.tan(angular_size / 2.0))
        # Frame widths per second → radians per second.
        angular_rate = image_speed * hfov
        speed_ms = range_m * angular_rate

        low, high = profile.typical_speed_ms
        plausible = low <= speed_ms <= high

        base.available = True
        base.range_m = round(range_m, 1)
        base.speed_ms = round(speed_ms, 1)
        # Derived from the rounded value so the two figures shown side by
        # side always agree with each other.
        base.speed_kmh = round(base.speed_ms * 3.6, 1)
        base.plausible = plausible
        base.detail = (
            f"Assumes {profile.label} ≈ {profile.characteristic_size_m:.2f} m across "
            f"at {self.camera_hfov_deg:.0f}° HFOV. Cross-range only."
        )
        if not plausible:
            base.detail += f" Outside typical {low:.0f}-{high:.0f} m/s for this class."
        return base


def build_speed_estimator(settings) -> SpeedEstimator:
    return SpeedEstimator(
        camera_hfov_deg=settings.camera_hfov_deg,
        enabled=settings.camera_hfov_deg > 0.0,
    )
