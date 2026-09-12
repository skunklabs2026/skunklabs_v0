"""Where tracks come from.

The defense scenario consumes `TrackReport`s and does not care who produced
them. V0 ships one producer, `SimulatedTrackSource`, laid out per threat
scenario by `scenario_track_sources`. The existing video / computer-vision
pipeline (`backend/pipeline/`) is the intended second one: an adapter that
turns a confirmed target into a `TrackReport` plugs in here without the state
machine, the API or the UI changing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.scenario.config import ScenarioConfig, ScenarioDefinition
from backend.scenario.geo import LatLon, bearing_deg, destination


@dataclass(frozen=True)
class TrackReport:
    """One sensor's latest statement about one air track."""

    track_id: str
    position: LatLon
    altitude_m: float
    heading_deg: float
    speed_kmh: float
    source: str


class TrackSource(Protocol):
    def advance(self, world_dt: float) -> TrackReport:
        """Move the source's clock on by `world_dt` seconds and report."""
        ...


class SimulatedTrackSource:
    """A constant-velocity drone on a straight line toward an aim point."""

    source = "SIMULATED"

    def __init__(
        self, track_id: str, start: LatLon, aim: LatLon, altitude_m: float, speed_kmh: float
    ) -> None:
        self._track_id = track_id
        self._position = start
        self._heading = bearing_deg(start, aim)
        self._altitude_m = altitude_m
        self._speed_kmh = speed_kmh

    def advance(self, world_dt: float) -> TrackReport:
        travelled = self._speed_kmh / 3.6 * world_dt
        self._position = destination(self._position, self._heading, travelled)
        return TrackReport(
            track_id=self._track_id,
            position=self._position,
            altitude_m=self._altitude_m,
            heading_deg=self._heading,
            speed_kmh=self._speed_kmh,
            source=self.source,
        )


def scenario_track_sources(
    config: ScenarioConfig, scenario: ScenarioDefinition, site: LatLon
) -> list[TrackSource]:
    """One drone per slot in each threat group, fanned out around the group's bearing.

    Every drone starts at the same range and flies at the site, so a group
    crosses into the protected radius together.
    """
    setup = config.track
    sources: list[TrackSource] = []
    for group in scenario.groups:
        for index in range(group.count):
            offset = (index - (group.count - 1) / 2) * setup.group_spread_deg
            start = destination(site, group.bearing_deg + offset, setup.spawn_range_km * 1000)
            sources.append(
                SimulatedTrackSource(
                    f"T-{len(sources) + 1:03d}",
                    start,
                    site,
                    setup.altitude_m,
                    setup.speed_kmh,
                )
            )
    return sources
