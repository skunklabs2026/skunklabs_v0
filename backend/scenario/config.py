"""Every tunable of the V0 defense scenario, in one place.

Change the demo here - layout, threat scenarios, speeds, timings - rather than
in the simulation.

Positions are relative. The protected site is wherever the operator's device
says it is (the frontend sends its GPS position; `SiteSetup` is only the
fallback), and the six nodes and every threat are laid out around it.

Time has two clocks:

* **Wall time** - what the audience experiences. Launcher slew, state holds
  and delays are in wall seconds, so launchers turn at a believable rate.
* **World time** - wall time multiplied by `TimingSetup.time_scale`. Only
  threats and interceptors move in world time, so displayed speeds stay
  realistic while a 40 km approach still fits a short demo. The UI labels the
  factor.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SiteSetup:
    """The infrastructure being protected, and the protected radius around it."""

    site_id: str = "SITE-A"
    name: str = "Protected infrastructure"
    # Used only until the operator's device reports its location.
    latitude: float = 49.993
    longitude: float = 36.230
    protected_radius_km: float = 40.0


@dataclass(frozen=True)
class NodeSetup:
    """The defensive nodes, evenly spaced on a ring around the site."""

    count: int = 6
    ring_radius_km: float = 20.0
    # Bearing of NODE-01 from the site; the rest follow clockwise.
    first_bearing_deg: float = 0.0
    # Drawn coverage per node. 25 km from a 20 km ring covers the whole 40 km
    # protected disc, so the union of the circles reads as the defended area.
    coverage_radius_km: float = 25.0
    inventory: int = 6
    inventory_capacity: int = 6
    neutral_pitch_deg: float = 0.0


@dataclass(frozen=True)
class ThreatGroup:
    """Drones approaching together from one direction."""

    # Where they come from, as a compass bearing from the site: 90 = east.
    bearing_deg: float
    count: int


@dataclass(frozen=True)
class ScenarioDefinition:
    id: str
    name: str
    description: str
    groups: tuple[ThreatGroup, ...]

    @property
    def threat_count(self) -> int:
        return sum(group.count for group in self.groups)


SCENARIOS: tuple[ScenarioDefinition, ...] = (
    ScenarioDefinition(
        "S1",
        "Scenario 1",
        "4 drones approaching from the east",
        (ThreatGroup(90.0, 4),),
    ),
    ScenarioDefinition(
        "S2",
        "Scenario 2",
        "3 drones from the east, 3 from the west",
        (ThreatGroup(90.0, 3), ThreatGroup(270.0, 3)),
    ),
    ScenarioDefinition(
        "S3",
        "Scenario 3",
        "4 drones from the north, 2 from the southeast",
        (ThreatGroup(0.0, 4), ThreatGroup(135.0, 2)),
    ),
)


@dataclass(frozen=True)
class TrackSetup:
    """How every simulated drone is placed and flown."""

    # Distance from the site where drones first appear - just outside the
    # protected radius, so they cross into it a few seconds after start.
    spawn_range_km: float = 44.0
    # Bearing spacing between drones of one group.
    group_spread_deg: float = 8.0
    altitude_m: float = 1000.0
    speed_kmh: float = 180.0
    trail_interval_s: float = 0.5
    trail_length: int = 40


@dataclass(frozen=True)
class OrientationSetup:
    """How each launcher visually slews. Display motion only - not a servo model."""

    yaw_max_rate_deg_s: float = 30.0
    yaw_accel_deg_s2: float = 75.0
    pitch_max_rate_deg_s: float = 10.0
    pitch_accel_deg_s2: float = 30.0
    # Proportional approach near the target: higher = snappier settle, and a
    # smaller steady lag while tracking a crossing threat.
    settle_gain_per_s: float = 4.0
    # Both axes within this of the requested orientation → READY.
    #
    # A node tracking a closing threat keeps a small standing lag (roughly the
    # threat's bearing rate ÷ settle_gain). READY must tolerate that lag, and
    # the realign threshold must sit well above it - otherwise a node that once
    # slipped out of READY could never return, and its response could never be
    # authorized.
    ready_tolerance_deg: float = 2.0
    # A READY launcher that drifts further than this goes back to ORIENTING.
    realign_threshold_deg: float = 6.0
    # Requested pitch is the line-of-sight elevation, but never below this
    # visual launch posture.
    min_launch_elevation_deg: float = 12.0
    max_elevation_deg: float = 60.0


@dataclass(frozen=True)
class EngagementSetup:
    """Proposed responses: one node paired with one threat."""

    # Interceptors proposed per threat. The operator can change it when
    # authorizing, up to the node's inventory.
    proposed_interceptors: int = 2
    # A beat between the first threat crossing the protected radius and pairing
    # threats with nodes, so one wave is assessed - and activates - together.
    assessment_delay_s: float = 0.5
    # TRACK_RECEIVED → ORIENTING.
    orient_delay_s: float = 0.6
    # AUTHORIZED → SIMULATED_LAUNCH.
    launch_delay_s: float = 1.0


@dataclass(frozen=True)
class InterceptorSetup:
    """The simulated interceptor markers."""

    # INT-001, INT-002, … numbered across the whole mission.
    id_prefix: str = "INT"
    speed_kmh: float = 600.0
    # Wall seconds between successive launches of one response.
    salvo_interval_s: float = 0.6
    # Marker-to-marker distance counted as the simulated intercept.
    intercept_radius_m: float = 200.0
    # Wall seconds before an interceptor that has not arrived faults the demo.
    max_flight_s: float = 30.0
    trail_interval_s: float = 0.2
    trail_length: int = 40


@dataclass(frozen=True)
class TimingSetup:
    """Demo pacing."""

    # World-time multiplier for threat and interceptor motion (see module doc).
    #
    # Sized so that a wave crosses the protected radius a few seconds after the
    # start, and the operator then has about a minute to work through the
    # queue one decision at a time before anything reaches the site.
    time_scale: float = 12.0
    # A threat this close to the site centre has reached it.
    site_reached_km: float = 1.5
    # Every threat resolved → COMPLETE after this hold.
    complete_delay_s: float = 2.0
    # Simulation ticks per second (and WebSocket pushes while running).
    tick_hz: float = 20.0
    # Events retained in the operator log.
    max_events: int = 60


@dataclass(frozen=True)
class ScenarioConfig:
    site: SiteSetup = field(default_factory=SiteSetup)
    nodes: NodeSetup = field(default_factory=NodeSetup)
    track: TrackSetup = field(default_factory=TrackSetup)
    orientation: OrientationSetup = field(default_factory=OrientationSetup)
    engagement: EngagementSetup = field(default_factory=EngagementSetup)
    interceptor: InterceptorSetup = field(default_factory=InterceptorSetup)
    timing: TimingSetup = field(default_factory=TimingSetup)
    scenarios: tuple[ScenarioDefinition, ...] = SCENARIOS
