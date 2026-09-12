"""Display geometry for the launcher scenario map."""

from __future__ import annotations

import pytest

from backend.scenario.geo import (
    LatLon,
    bearing_deg,
    destination,
    elevation_deg,
    ground_distance_m,
    offset_m,
    shortest_delta,
    wrap_360,
)

NODE = LatLon(49.993, 36.230)


@pytest.mark.parametrize(
    ("deg", "expected"),
    [(0.0, 0.0), (360.0, 0.0), (-10.0, 350.0), (725.0, 5.0), (-1e-15, 0.0)],
)
def test_wrap_360(deg, expected):
    assert wrap_360(deg) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (0.0, 72.0, 72.0),
        (350.0, 10.0, 20.0),  # through north, not the long way round
        (10.0, 350.0, -20.0),
        (0.0, 180.0, 180.0),
        (180.0, 0.0, 180.0),  # exactly opposite resolves to +180, never -180
    ],
)
def test_shortest_delta(start, end, expected):
    assert shortest_delta(start, end) == pytest.approx(expected)


@pytest.mark.parametrize("bearing", [0.0, 72.0, 90.0, 180.0, 271.5])
def test_destination_round_trips_through_bearing_and_distance(bearing):
    point = destination(NODE, bearing, 32_000.0)
    assert bearing_deg(NODE, point) == pytest.approx(bearing, abs=1e-6)
    assert ground_distance_m(NODE, point) == pytest.approx(32_000.0, rel=1e-9)


def test_compass_convention():
    """0° is north and bearings run clockwise - east is 90°."""
    east, north = offset_m(NODE, destination(NODE, 90.0, 1000.0))
    assert east == pytest.approx(1000.0)
    assert north == pytest.approx(0.0, abs=1e-6)
    assert bearing_deg(NODE, LatLon(NODE.lat + 0.1, NODE.lon)) == pytest.approx(0.0)


def test_elevation():
    assert elevation_deg(1000.0, 1000.0) == pytest.approx(45.0)
    assert elevation_deg(0.0, 100.0) == pytest.approx(90.0)
