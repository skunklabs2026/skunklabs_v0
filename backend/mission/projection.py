"""Track projection - the operator-facing view of image-plane extrapolation.

`trajectory.py` does the maths. This module turns its output into the four
things an operator can legitimately be told from an uncalibrated camera:

    DIRECTION               where the track is heading within the frame
    TRACK STABILITY         how consistently it is moving
    PREDICTION HORIZON      how far ahead the extrapolation extends
    PROJECTION CONFIDENCE   how well the motion model fits

>>> WHY THIS EXISTS <<<
The earlier console displayed "time to impact" and "intercept in" as if they
were a firing solution. They were not: they are the output of a geometric
puzzle in normalised image coordinates with no range, no altitude and no
camera calibration. Presenting them as seconds-until-something-happens is
false precision of the worst kind, because it looks like a measurement.

Everything here is explicitly framed as a *sensor-frame projection*, and the
UI labels it that way.
"""

from __future__ import annotations

import math

from backend.schemas import TrackProjection, TrackStability, Trajectory

# Projection confidence bands. A projection below the first band is not shown
# as a direction at all - an unstable track has no meaningful heading.
_STABLE = 0.60
_SETTLING = 0.30

# Below this speed (frame widths per second) the track is effectively
# stationary in the image and any "direction" is fitting noise.
_MIN_SPEED = 0.01

# Compass-style sectors within the sensor frame, starting at frame-up and
# going clockwise in 45° steps.
_SECTORS = (
    "UP",
    "UP / RIGHT",
    "RIGHT",
    "DOWN / RIGHT",
    "DOWN",
    "DOWN / LEFT",
    "LEFT",
    "UP / LEFT",
)


def _stability(confidence: float) -> TrackStability:
    if confidence >= _STABLE:
        return TrackStability.STABLE
    if confidence >= _SETTLING:
        return TrackStability.SETTLING
    return TrackStability.UNSTABLE


def _direction(vx: float, vy: float) -> tuple[float, str]:
    """Heading within the frame, degrees clockwise from frame-up.

    Image y grows downward, so frame-up is -y. Working in this frame keeps
    the label honest: it describes motion across the sensor, and is never
    mistaken for a compass bearing.
    """
    degrees = math.degrees(math.atan2(vx, -vy)) % 360.0
    sector = _SECTORS[int((degrees + 22.5) % 360.0 // 45.0)]
    return degrees, sector


def build_track_projection(trajectory: Trajectory | None) -> TrackProjection:
    """Present a trajectory as a sensor-frame projection."""
    if trajectory is None or not trajectory.valid:
        return TrackProjection(valid=False)

    velocity = trajectory.velocity
    stability = _stability(trajectory.confidence)

    direction_deg: float | None = None
    direction_label = "-"
    if velocity is not None and velocity.speed >= _MIN_SPEED:
        direction_deg, direction_label = _direction(velocity.x, velocity.y)

    return TrackProjection(
        valid=True,
        direction_deg=direction_deg,
        direction_label=direction_label,
        stability=stability,
        horizon=trajectory.horizon,
        confidence=trajectory.confidence,
        points=list(trajectory.points),
    )
