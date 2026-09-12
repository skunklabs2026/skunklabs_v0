"""Geometry for a map display a few tens of kilometres across.

Flat-earth (equirectangular) about a local origin. Over the ~40 km the demo
covers, the error is a few metres - invisible on a tactical map, and far
simpler to read than great-circle maths. This is display geometry, not
navigation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

METERS_PER_DEG_LAT = 111_320.0


@dataclass(frozen=True)
class LatLon:
    lat: float
    lon: float


def _meters_per_deg_lon(lat: float) -> float:
    return METERS_PER_DEG_LAT * math.cos(math.radians(lat))


def wrap_360(deg: float) -> float:
    """Normalise to [0, 360)."""
    wrapped = deg % 360.0
    # -1e-15 % 360 == 360.0 in floating point.
    return 0.0 if wrapped >= 360.0 else wrapped


def shortest_delta(from_deg: float, to_deg: float) -> float:
    """Signed smallest rotation from one heading to another, in (-180, 180]."""
    delta = (to_deg - from_deg + 180.0) % 360.0 - 180.0
    return 180.0 if delta == -180.0 else delta


def offset_m(origin: LatLon, point: LatLon) -> tuple[float, float]:
    """(east, north) metres of `point` relative to `origin`."""
    east = (point.lon - origin.lon) * _meters_per_deg_lon(origin.lat)
    north = (point.lat - origin.lat) * METERS_PER_DEG_LAT
    return east, north


def ground_distance_m(a: LatLon, b: LatLon) -> float:
    east, north = offset_m(a, b)
    return math.hypot(east, north)


def bearing_deg(origin: LatLon, point: LatLon) -> float:
    """Compass bearing from `origin` to `point` (0° = north, clockwise)."""
    east, north = offset_m(origin, point)
    return wrap_360(math.degrees(math.atan2(east, north)))


def destination(origin: LatLon, bearing: float, distance_m: float) -> LatLon:
    """The point `distance_m` from `origin` along compass `bearing`."""
    rad = math.radians(bearing)
    east = math.sin(rad) * distance_m
    north = math.cos(rad) * distance_m
    return LatLon(
        lat=origin.lat + north / METERS_PER_DEG_LAT,
        lon=origin.lon + east / _meters_per_deg_lon(origin.lat),
    )


def elevation_deg(ground_m: float, height_m: float) -> float:
    """Line-of-sight elevation angle to something `height_m` up, `ground_m` away."""
    return math.degrees(math.atan2(height_m, max(ground_m, 1e-6)))
