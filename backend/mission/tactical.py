"""The local tactical picture.

Turns the current tracks into a plan-style view: the canister at the origin,
its detection sector opening upward, and each track plotted by where it sits
within that sector.

>>> SCOPE - READ THIS BEFORE ADDING A FIELD <<<
There is no GPS, no compass, no rangefinder and no camera calibration in V0.
Everything this module produces is *relative to the sensor frame*, and the
model says so in three places: the `frame` discriminator, the `frame_label`
shown on the view, and the per-track `bearing_available` / `range_available`
flags, which are False.

The structure is built for the sources that come later - a calibrated sensor,
an external track feed, a second canister. Those add producers and set the
availability flags; they do not change the view. Anything that would require
inventing a geographic quantity does not belong here.
"""

from __future__ import annotations

import math

from backend.schemas import (
    PlatformClass,
    Point,
    TacticalFrame,
    TacticalPicture,
    TacticalTrack,
    Target,
)

# The label carried on the view itself, so a screenshot taken out of context
# still states what frame it is in.
RELATIVE_LABEL = "LOCAL TRACK · RELATIVE COORDINATES · SENSOR FRAME"
CALIBRATED_LABEL = "LOCAL TRACK · SENSOR FRAME · CALIBRATED FOV"

SENSOR_SOURCE = "CANISTER_01/SENSOR_01"


def _course(target: Target) -> tuple[float, float, float]:
    """Unit direction of travel in the sensor frame, plus speed.

    Taken from the fitted trajectory when there is one. A track with no fit
    yet gets a zero vector, and the view draws no arrow rather than a
    meaningless one.
    """
    trajectory = target.trajectory
    if trajectory is None or not trajectory.valid or trajectory.velocity is None:
        return 0.0, 0.0, 0.0

    vx, vy = trajectory.velocity.x, trajectory.velocity.y
    speed = math.hypot(vx, vy)
    if speed <= 0.0:
        return 0.0, 0.0, 0.0
    return vx / speed, vy / speed, trajectory.velocity.speed


def _projected_path(target: Target) -> list[Point]:
    """The track's projected path, as future bearing/elevation pairs.

    Bearing and elevation only. Range was never measured, so it cannot be
    extrapolated - the view holds the track's current depth along the whole
    path rather than implying a closing rate the sensor cannot see.
    """
    projection = target.projection
    if projection is None or not projection.valid:
        return []
    return [
        Point(
            x=max(-1.0, min(1.0, (point.x - 0.5) * 2.0)),
            y=max(0.0, min(1.0, point.y)),
        )
        for point in projection.points
    ]


def _track_from_target(target: Target, *, fov_deg: float | None) -> TacticalTrack:
    centre_x = target.bbox.x + target.bbox.width / 2.0
    centre_y = target.bbox.y + target.bbox.height / 2.0

    # Map the horizontal frame position onto -1..+1 across the field of view,
    # so 0 is boresight. This is a *relative* offset, not a bearing.
    bearing_norm = max(-1.0, min(1.0, (centre_x - 0.5) * 2.0))
    course_x, course_y, speed = _course(target)

    # An angle is only meaningful once the field of view is known. Without it
    # the value stays null and the view says so.
    bearing_deg = (bearing_norm * fov_deg / 2.0) if fov_deg else None

    return TacticalTrack(
        target_id=target.target_id,
        is_primary=target.is_primary,
        bearing_norm=bearing_norm,
        elevation_norm=max(0.0, min(1.0, centre_y)),
        apparent_size=target.bbox.width,
        course_x=course_x,
        course_y=course_y,
        speed_norm=speed,
        bearing_available=bearing_deg is not None,
        bearing_deg=bearing_deg,
        # V0 has no rangefinder. The speed estimator can *infer* a range from
        # an assumed airframe size, but that is an assumption stacked on a
        # classification, and it has no place on a tactical plot where it
        # would read as a measured distance.
        range_available=False,
        range_m=None,
        path=_projected_path(target),
        confidence=target.confidence,
        platform=target.platform or PlatformClass.UNKNOWN,
        track_duration=target.track_duration,
        source=SENSOR_SOURCE,
    )


def build_tactical_picture(
    targets: list[Target], *, camera_hfov_deg: float = 0.0
) -> TacticalPicture:
    """Assemble the tactical picture for one frame.

    Only *confirmed* tracks are plotted. A tactical picture is a picture of
    what the canister is holding, and an unconfirmed detection is not yet
    that - it is a candidate the tracker has seen once or twice and may drop
    on the next frame. Plotting them filled the view with anonymous marks
    (they share the designation "UNCONFIRMED", so they were not even
    distinguishable from one another) and buried the one track that mattered.
    They are still reported, as a count.
    """
    calibrated = camera_hfov_deg > 0.0
    fov = camera_hfov_deg if calibrated else None

    confirmed = [t for t in targets if t.tracking]

    return TacticalPicture(
        frame=TacticalFrame.SENSOR_FRAME,
        frame_label=CALIBRATED_LABEL if calibrated else RELATIVE_LABEL,
        fov_deg=fov,
        calibrated=calibrated,
        tracks=[_track_from_target(t, fov_deg=fov) for t in confirmed],
        candidates=len(targets) - len(confirmed),
        sources=[SENSOR_SOURCE],
    )
