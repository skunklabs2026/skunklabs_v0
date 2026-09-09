"""Sensor-frame track projection and the tactical picture.

These tests exist mostly to pin down what the system must *not* claim. The
console previously showed "time to impact" from an uncalibrated camera; the
assertions below are what stops that coming back.
"""

from __future__ import annotations

import pytest

from backend.mission.projection import build_track_projection
from backend.mission.tactical import build_tactical_picture
from backend.schemas import (
    BBox,
    PlatformClass,
    TacticalFrame,
    Target,
    TrackProjection,
    TrackStability,
    Trajectory,
    TrajectoryPoint,
    Velocity,
)


def trajectory(
    *, vx: float = 0.0, vy: float = 0.0, confidence: float = 0.9, valid: bool = True
) -> Trajectory:
    speed = (vx**2 + vy**2) ** 0.5
    return Trajectory(
        valid=valid,
        points=[TrajectoryPoint(x=0.5, y=0.5, t=0.0)],
        velocity=Velocity(x=vx, y=vy, speed=speed),
        confidence=confidence,
        horizon=2.0,
    )


def target(**overrides) -> Target:
    base = dict(
        target_id="UAV-001",
        object_class="uav",
        confidence=0.9,
        bbox=BBox(x=0.4, y=0.3, width=0.1, height=0.08),
        tracking=True,
        age_frames=10,
        track_duration=3.0,
        is_primary=True,
    )
    base.update(overrides)
    return Target(**base)


class TestTrackProjection:
    def test_invalid_trajectory_yields_no_projection(self):
        assert build_track_projection(None).valid is False
        assert build_track_projection(trajectory(valid=False)).valid is False

    def test_direction_is_expressed_in_the_sensor_frame(self):
        """Image y grows downward, so a negative vy is UP on screen."""
        assert build_track_projection(trajectory(vy=-0.5)).direction_label == "UP"
        assert build_track_projection(trajectory(vx=0.5)).direction_label == "RIGHT"
        assert build_track_projection(trajectory(vy=0.5)).direction_label == "DOWN"
        assert build_track_projection(trajectory(vx=-0.5)).direction_label == "LEFT"

    def test_a_barely_moving_track_gets_no_direction(self):
        """Fitting a heading to noise is exactly the false precision to avoid."""
        projection = build_track_projection(trajectory(vx=0.0001))
        assert projection.direction_deg is None
        assert projection.direction_label == "—"

    def test_stability_bands(self):
        assert build_track_projection(
            trajectory(vx=0.5, confidence=0.9)
        ).stability is TrackStability.STABLE
        assert build_track_projection(
            trajectory(vx=0.5, confidence=0.4)
        ).stability is TrackStability.SETTLING
        assert build_track_projection(
            trajectory(vx=0.5, confidence=0.1)
        ).stability is TrackStability.UNSTABLE

    def test_the_frame_is_always_declared(self):
        assert build_track_projection(trajectory(vx=0.5)).frame == "SENSOR_FRAME"


class TestTacticalPicture:
    def test_uncalibrated_picture_declares_itself_relative(self):
        picture = build_tactical_picture([target()])
        assert picture.frame is TacticalFrame.SENSOR_FRAME
        assert picture.calibrated is False
        assert picture.fov_deg is None
        assert "RELATIVE" in picture.frame_label

    def test_no_bearing_or_range_without_calibration(self):
        """The one guarantee that keeps the tactical view honest."""
        track = build_tactical_picture([target()]).tracks[0]
        assert track.bearing_available is False
        assert track.bearing_deg is None
        assert track.range_available is False
        assert track.range_m is None

    def test_bearing_appears_once_the_fov_is_configured(self):
        # Target centred at x=0.45 → 0.1 left of boresight → -0.1 of half-FOV.
        track = build_tactical_picture([target()], camera_hfov_deg=60.0).tracks[0]
        assert track.bearing_available is True
        assert track.bearing_deg == pytest.approx(-3.0)

    def test_range_stays_unavailable_even_when_calibrated(self):
        """A field of view gives an angle, never a distance.

        Range would require an assumed airframe size stacked on a kinematic
        classification — an inference, not a measurement, and it has no place
        on a plot where it would read as one.
        """
        track = build_tactical_picture([target()], camera_hfov_deg=60.0).tracks[0]
        assert track.range_available is False

    def test_boresight_is_zero_and_edges_are_unit(self):
        centred = build_tactical_picture(
            [target(bbox=BBox(x=0.45, y=0.4, width=0.1, height=0.1))]
        ).tracks[0]
        assert centred.bearing_norm == pytest.approx(0.0)

        right = build_tactical_picture(
            [target(bbox=BBox(x=0.9, y=0.4, width=0.1, height=0.1))]
        ).tracks[0]
        assert right.bearing_norm == pytest.approx(0.9)

    def test_track_with_no_fit_gets_no_course_arrow(self):
        track = build_tactical_picture([target()]).tracks[0]
        assert (track.course_x, track.course_y) == (0.0, 0.0)

    def test_course_is_a_unit_vector(self):
        track = build_tactical_picture(
            [target(trajectory=trajectory(vx=0.3, vy=-0.4))]
        ).tracks[0]
        assert (track.course_x**2 + track.course_y**2) == pytest.approx(1.0)
        assert track.speed_norm == pytest.approx(0.5)

    def test_every_track_names_its_source(self):
        """Extensibility: a second canister's tracks must be distinguishable."""
        picture = build_tactical_picture([target()])
        assert picture.tracks[0].source in picture.sources

    def test_platform_defaults_to_unknown(self):
        assert build_tactical_picture([target()]).tracks[0].platform is (
            PlatformClass.UNKNOWN
        )


class TestTacticalDeclutter:
    """Only confirmed tracks are plotted; candidates are counted.

    Unconfirmed tracks all share the designation "UNCONFIRMED", so plotting
    them produced a pile of identical, indistinguishable labels that buried
    the one track the mission was acting on.
    """

    def test_unconfirmed_tracks_are_not_plotted(self):
        picture = build_tactical_picture(
            [
                target(),
                target(target_id="UNCONFIRMED", tracking=False, is_primary=False),
                target(target_id="UNCONFIRMED", tracking=False, is_primary=False),
            ]
        )
        assert [t.target_id for t in picture.tracks] == ["UAV-001"]

    def test_unconfirmed_tracks_are_still_counted(self):
        """The operator must know the sensor is busy, without the plot filling."""
        picture = build_tactical_picture(
            [
                target(),
                target(target_id="UNCONFIRMED", tracking=False, is_primary=False),
                target(target_id="UNCONFIRMED", tracking=False, is_primary=False),
            ]
        )
        assert picture.candidates == 2

    def test_plotted_track_ids_are_unique(self):
        """They are React keys, and duplicates silently corrupt the render."""
        picture = build_tactical_picture(
            [
                target(),
                target(target_id="UAV-002", is_primary=False),
                target(target_id="UNCONFIRMED", tracking=False, is_primary=False),
            ]
        )
        ids = [t.target_id for t in picture.tracks]
        assert len(ids) == len(set(ids))

    def test_no_confirmed_tracks_yields_an_empty_plot(self):
        picture = build_tactical_picture(
            [target(target_id="UNCONFIRMED", tracking=False, is_primary=False)]
        )
        assert picture.tracks == []
        assert picture.candidates == 1


class TestProjectedPath:
    def test_track_without_a_projection_has_no_path(self):
        assert build_tactical_picture([target()]).tracks[0].path == []

    def test_path_is_expressed_as_bearings(self):
        """Frame x of 0..1 maps onto bearing -1..+1."""
        projected = TrackProjection(
            valid=True,
            points=[
                TrajectoryPoint(x=0.5, y=0.5, t=0.0),
                TrajectoryPoint(x=0.75, y=0.4, t=1.0),
            ],
        )
        path = build_tactical_picture(
            [target(projection=projected)]
        ).tracks[0].path
        assert [round(p.x, 3) for p in path] == [0.0, 0.5]

    def test_path_bearings_are_clamped_to_the_sector(self):
        """An extrapolation may run off-frame; the plot must not."""
        projected = TrackProjection(
            valid=True,
            points=[TrajectoryPoint(x=3.0, y=0.5, t=1.0)],
        )
        path = build_tactical_picture(
            [target(projection=projected)]
        ).tracks[0].path
        assert path[0].x == 1.0

    def test_invalid_projection_yields_no_path(self):
        path = build_tactical_picture(
            [target(projection=TrackProjection(valid=False))]
        ).tracks[0].path
        assert path == []
