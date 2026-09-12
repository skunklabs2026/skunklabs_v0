"""The V0 defense scenario: six nodes, several threats, one decision queue.

    Mission   IDLE → RUNNING → COMPLETE                                  (FAULT)
    Node      STANDBY → TRACK_RECEIVED → ORIENTING → READY
                      → AUTHORIZED → SIMULATED_LAUNCH → STANDBY
    Response  PROPOSED → AWAITING_AUTHORIZATION → AUTHORIZED → IN_FLIGHT → INTERCEPTED
                         └─ DECLINED               (ABORTED if the threat reaches the site)

The story: a protected site at the operator's location, six nodes around it,
drones inbound. When threats cross into the protected radius, each is paired
with its nearest free node - every pair in the same tick, so those nodes
activate together. Each pair is a proposed response. The nodes orient; the
operator authorizes or declines each response individually; authorized nodes
launch a short salvo; the first interceptor to reach the threat is the
simulated intercept, and the node is free for the next threat.

Pure and deterministic: no threads, no I/O, no wall clock except for event
timestamps. `step(dt)` advances everything; tests drive it directly.

Two rules the structure enforces:

* **Authorization is explicit and individual.** A response only reaches
  AUTHORIZED through `authorize(response_id)`, one response per call, and only
  once its node is READY. No timer or proximity can authorize anything.
* **Nothing here is fire control.** Requested yaw is the bearing to the
  threat, requested pitch its line-of-sight elevation with a minimum display
  posture, and an interceptor is a marker that walks toward the threat marker.
  There is no ballistic model, no lead, and no guidance law.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from backend.scenario.config import ScenarioConfig, ScenarioDefinition
from backend.scenario.geo import (
    LatLon,
    bearing_deg,
    destination,
    elevation_deg,
    ground_distance_m,
    shortest_delta,
    wrap_360,
)
from backend.scenario.models import (
    DefenseNode,
    Engagement,
    EngagementStatus,
    GeoPoint,
    InterceptorStatus,
    LocationSource,
    MissionState,
    NodeState,
    ProtectedSite,
    ScenarioEvent,
    ScenarioOption,
    ScenarioSnapshot,
    SimulatedInterceptor,
    Track,
    TrackStatus,
)
from backend.scenario.track_source import TrackReport, TrackSource, scenario_track_sources

TrackSourceFactory = Callable[[ScenarioConfig, ScenarioDefinition, LatLon], list[TrackSource]]

# A stalled event loop must not teleport threats across the map.
MAX_STEP_S = 0.25
# Below these, a slewing axis has arrived rather than creeping in forever.
_SETTLE_DEG = 0.01
_SETTLE_RATE_DEG_S = 0.5

# A node follows its threat with its orientation in these states.
_SLEWING = frozenset(
    {NodeState.ORIENTING, NodeState.READY, NodeState.AUTHORIZED, NodeState.SIMULATED_LAUNCH}
)
# Responses still waiting for the operator.
_UNDECIDED = frozenset({EngagementStatus.PROPOSED, EngagementStatus.AWAITING_AUTHORIZATION})
# Responses that still hold their node.
_ACTIVE = _UNDECIDED | {EngagementStatus.AUTHORIZED, EngagementStatus.IN_FLIGHT}


@dataclass(frozen=True)
class CommandOutcome:
    ok: bool
    detail: str


@dataclass
class _Axis:
    """One visual rotation axis: where it points, where it is asked to point."""

    position: float
    target: float
    rate: float = 0.0

    def error(self, *, wrap: bool) -> float:
        if wrap:
            return shortest_delta(self.position, self.target)
        return self.target - self.position


def slew_axis(
    axis: _Axis, dt: float, *, max_rate: float, accel: float, gain: float, wrap: bool
) -> None:
    """Move an axis toward its target with a rate limit and an acceleration limit.

    Proportional near the target, so it settles instead of stopping dead, and
    never steps past the target. Takes the short way round on a wrapped axis.
    """
    error = axis.error(wrap=wrap)
    desired = max(-max_rate, min(max_rate, gain * error))
    max_change = accel * dt
    axis.rate += max(-max_change, min(max_change, desired - axis.rate))
    step = axis.rate * dt
    arrived = abs(error - step) < _SETTLE_DEG and abs(axis.rate) < _SETTLE_RATE_DEG_S
    if error == 0.0 or arrived or (step * error > 0 and abs(step) >= abs(error)):
        axis.position = axis.target
        axis.rate = 0.0
    else:
        axis.position += step
    if wrap:
        axis.position = wrap_360(axis.position)


@dataclass
class _Track:
    source: TrackSource
    report: TrackReport
    trail: deque[LatLon]
    status: TrackStatus = TrackStatus.INBOUND
    since_breadcrumb: float = 0.0
    inside: bool = False
    engagement_id: str | None = None
    declined: bool = False

    @property
    def id(self) -> str:
        return self.report.track_id


@dataclass
class _Interceptor:
    id: str
    node_id: str
    track_id: str
    engagement_id: str
    position: LatLon
    heading: float
    trail: deque[LatLon]
    status: InterceptorStatus = InterceptorStatus.PENDING
    flight_s: float = 0.0
    since_breadcrumb: float = 0.0


@dataclass
class _Engagement:
    id: str
    node_id: str
    track_id: str
    proposed: int
    status: EngagementStatus = EngagementStatus.PROPOSED
    interceptors: list[_Interceptor] = field(default_factory=list)
    intercept_point: LatLon | None = None


@dataclass
class _Node:
    id: str
    position: LatLon
    yaw: _Axis
    pitch: _Axis
    inventory: int
    state: NodeState = NodeState.STANDBY
    in_state: float = 0.0
    engagement: _Engagement | None = None


def _geo(point: LatLon) -> GeoPoint:
    return GeoPoint(latitude=round(point.lat, 6), longitude=round(point.lon, 6))


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


class DefenseScenario:
    def __init__(
        self,
        config: ScenarioConfig | None = None,
        *,
        clock: Callable[[], float] = time.time,
        track_source_factory: TrackSourceFactory | None = None,
    ) -> None:
        self.config = config or ScenarioConfig()
        self._timestamp = clock
        self._track_source_factory = track_source_factory or scenario_track_sources
        self._events: deque[ScenarioEvent] = deque(maxlen=self.config.timing.max_events)
        self.scenario = self.config.scenarios[0]
        self._site = LatLon(self.config.site.latitude, self.config.site.longitude)
        self.location_source = LocationSource.DEFAULT
        self._init_state()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def configure(
        self,
        *,
        scenario_id: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> CommandOutcome:
        """Choose the threat scenario and/or centre everything on a location."""
        if self.running or self.state is not MissionState.IDLE:
            return CommandOutcome(
                False, "Reset the demo before changing the scenario or location."
            )
        if (latitude is None) != (longitude is None):
            return CommandOutcome(False, "A location needs both latitude and longitude.")
        if scenario_id is not None:
            match = next((s for s in self.config.scenarios if s.id == scenario_id), None)
            if match is None:
                known = ", ".join(s.id for s in self.config.scenarios)
                return CommandOutcome(
                    False, f"Unknown scenario {scenario_id!r} - choose one of {known}."
                )
            self.scenario = match
        if latitude is not None and longitude is not None:
            self._site = LatLon(latitude, longitude)
            self.location_source = LocationSource.DEVICE
        self._init_state()
        return CommandOutcome(True, f"{self.scenario.name} ready.")

    def start(self) -> CommandOutcome:
        if self.running or self.state is not MissionState.IDLE:
            return CommandOutcome(False, "Demo already started. Reset to run it again.")

        self.running = True
        self.state = MissionState.RUNNING
        trail_length = self.config.track.trail_length
        for source in self._track_source_factory(self.config, self.scenario, self._site):
            report = source.advance(0.0)
            self._tracks.append(
                _Track(
                    source=source,
                    report=report,
                    trail=deque([report.position], maxlen=trail_length),
                )
            )
        self._emit(f"{self.scenario.name} started - {self.scenario.description}")
        self._emit(
            f"External sensor reports {_plural(len(self._tracks), 'track')} inbound "
            f"to {self.config.site.site_id}"
        )
        return CommandOutcome(True, "Demo started.")

    def authorize(self, engagement_id: str, interceptors: int | None = None) -> CommandOutcome:
        """Authorize one proposed response, with the proposed or a chosen interceptor count."""
        engagement = self._find_engagement(engagement_id)
        if engagement is None:
            return CommandOutcome(False, f"No response {engagement_id}.")
        if engagement.status is not EngagementStatus.AWAITING_AUTHORIZATION:
            return CommandOutcome(
                False,
                f"Authorization rejected - {engagement.id} is {engagement.status.value}, "
                "not AWAITING_AUTHORIZATION.",
            )
        node = self._node(engagement.node_id)
        count = engagement.proposed if interceptors is None else interceptors
        if count < 1:
            return CommandOutcome(
                False, "Authorization rejected - select at least one interceptor."
            )
        if count > node.inventory:
            return CommandOutcome(
                False,
                f"Authorization rejected - only {_plural(node.inventory, 'interceptor')} "
                f"available at {node.id}.",
            )

        setup = self.config.interceptor
        for _ in range(count):
            self._interceptor_seq += 1
            engagement.interceptors.append(
                _Interceptor(
                    id=f"{setup.id_prefix}-{self._interceptor_seq:03d}",
                    node_id=node.id,
                    track_id=engagement.track_id,
                    engagement_id=engagement.id,
                    position=node.position,
                    heading=node.yaw.position,
                    trail=deque([node.position], maxlen=setup.trail_length),
                )
            )
        engagement.status = EngagementStatus.AUTHORIZED
        self._set_state(node, NodeState.AUTHORIZED)
        self._emit(
            f"{engagement.id} authorized by operator - {node.id} → {engagement.track_id}, "
            f"{_plural(count, 'interceptor')}"
        )
        return CommandOutcome(True, f"{engagement.id} authorized.")

    def decline(self, engagement_id: str) -> CommandOutcome:
        """Decline one response: its node is released, and the threat is not re-proposed."""
        engagement = self._find_engagement(engagement_id)
        if engagement is None:
            return CommandOutcome(False, f"No response {engagement_id}.")
        if engagement.status not in _UNDECIDED:
            return CommandOutcome(
                False,
                f"{engagement.id} is {engagement.status.value}; only a proposed response "
                "can be declined.",
            )
        engagement.status = EngagementStatus.DECLINED
        self._track(engagement.track_id).declined = True
        self._release(self._node(engagement.node_id))
        self._emit(
            f"{engagement.id} declined by operator - {engagement.track_id} not engaged "
            f"by {engagement.node_id}"
        )
        return CommandOutcome(True, f"{engagement.id} declined.")

    def reassign(self, engagement_id: str, node_id: str) -> CommandOutcome:
        """Hand one proposed response to a node the operator picked instead.

        The pairing the system proposes is the nearest free node; this is how
        the operator overrides it. The chosen node must be free and hold
        interceptors, and it starts orienting from wherever it is pointing.
        """
        engagement = self._find_engagement(engagement_id)
        if engagement is None:
            return CommandOutcome(False, f"No response {engagement_id}.")
        if engagement.status not in _UNDECIDED:
            return CommandOutcome(
                False,
                f"{engagement.id} is {engagement.status.value}; only a proposed response "
                "can be reassigned.",
            )
        if engagement.node_id == node_id:
            return CommandOutcome(False, f"{engagement.id} is already assigned to {node_id}.")
        target = next((n for n in self._nodes if n.id == node_id), None)
        if target is None:
            return CommandOutcome(False, f"No node {node_id}.")
        if target.engagement is not None:
            return CommandOutcome(
                False, f"{target.id} is already answering {target.engagement.track_id}."
            )
        if target.inventory <= 0:
            return CommandOutcome(False, f"{target.id} has no interceptors left.")

        previous = self._node(engagement.node_id)
        self._release(previous)
        engagement.node_id = target.id
        engagement.status = EngagementStatus.PROPOSED
        engagement.proposed = min(engagement.proposed, target.inventory)
        target.engagement = engagement
        self._set_state(target, NodeState.TRACK_RECEIVED)
        self._aim(target, self._track(engagement.track_id))
        self._emit(
            f"{engagement.id} reassigned by operator: {previous.id} to {target.id} "
            f"for {engagement.track_id}"
        )
        return CommandOutcome(True, f"{engagement.id} reassigned to {target.id}.")

    def reset(self) -> CommandOutcome:
        """Back to the start of the configured scenario, at the configured location."""
        self._init_state()
        return CommandOutcome(True, "Demo reset.")

    def fail(self, reason: str) -> None:
        self.running = False
        self.fault = reason
        self.state = MissionState.FAULT
        self._emit(f"Fault - {reason}")

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def step(self, dt: float) -> bool:
        """Advance wall time by `dt` seconds. Returns False when nothing moves."""
        if not self.running:
            return False

        dt = max(0.0, min(dt, MAX_STEP_S))
        world_dt = dt * self.config.timing.time_scale
        self._elapsed += dt
        for node in self._nodes:
            node.in_state += dt

        self._advance_tracks(dt, world_dt)
        self._assign_nodes(dt)
        for node in self._nodes:
            self._advance_node(node, dt)
        self._advance_interceptors(dt, world_dt)
        if self.running:
            self._check_complete(dt)
        return True

    def snapshot(self) -> ScenarioSnapshot:
        site, nodes = self.config.site, self.config.nodes
        return ScenarioSnapshot(
            state=self.state,
            scenario_id=self.scenario.id,
            scenarios=[
                ScenarioOption(
                    id=s.id, name=s.name, description=s.description, threat_count=s.threat_count
                )
                for s in self.config.scenarios
            ],
            running=self.running,
            elapsed_s=round(self._elapsed, 2),
            time_scale=self.config.timing.time_scale,
            site=ProtectedSite(
                id=site.site_id,
                name=site.name,
                latitude=round(self._site.lat, 6),
                longitude=round(self._site.lon, 6),
                protected_radius_km=site.protected_radius_km,
                location_source=self.location_source,
            ),
            nodes=[
                DefenseNode(
                    id=node.id,
                    latitude=round(node.position.lat, 6),
                    longitude=round(node.position.lon, 6),
                    coverage_radius_km=nodes.coverage_radius_km,
                    current_yaw_deg=round(node.yaw.position, 2),
                    target_yaw_deg=round(node.yaw.target, 2),
                    current_pitch_deg=round(node.pitch.position, 2),
                    target_pitch_deg=round(node.pitch.target, 2),
                    state=node.state,
                    engagement_id=node.engagement.id if node.engagement else None,
                    inventory=node.inventory,
                    inventory_capacity=nodes.inventory_capacity,
                )
                for node in self._nodes
            ],
            tracks=[self._track_model(track) for track in self._tracks],
            engagements=[self._engagement_model(e) for e in self._engagements],
            interceptors=[
                self._interceptor_model(i) for e in self._engagements for i in e.interceptors
            ],
            decision_queue=[e.id for e in self._engagements if e.status in _UNDECIDED],
            can_start=self.state is MissionState.IDLE and not self.running,
            can_configure=self.state is MissionState.IDLE and not self.running,
            fault=self.fault,
            events=list(self._events),
        )

    # ------------------------------------------------------------------
    # Internals: state
    # ------------------------------------------------------------------

    def _init_state(self) -> None:
        setup = self.config.nodes
        self.state = MissionState.IDLE
        self.running = False
        self.fault: str | None = None
        self._elapsed = 0.0
        self._since_resolved = 0.0
        self._since_waiting = 0.0
        self._tracks: list[_Track] = []
        self._engagements: list[_Engagement] = []
        self._engagement_seq = 0
        self._interceptor_seq = 0
        self._nodes: list[_Node] = []
        for index in range(setup.count):
            # Evenly spaced on the ring, each facing outward from the site.
            bearing = wrap_360(setup.first_bearing_deg + index * 360.0 / setup.count)
            self._nodes.append(
                _Node(
                    id=f"NODE-{index + 1:02d}",
                    position=destination(self._site, bearing, setup.ring_radius_km * 1000),
                    yaw=_Axis(position=bearing, target=bearing),
                    pitch=_Axis(
                        position=setup.neutral_pitch_deg, target=setup.neutral_pitch_deg
                    ),
                    inventory=setup.inventory,
                )
            )
        self._events.clear()

    def _emit(self, message: str) -> None:
        self._events.append(ScenarioEvent(timestamp=self._timestamp(), message=message))

    def _set_state(self, node: _Node, state: NodeState) -> None:
        node.state = state
        node.in_state = 0.0

    def _release(self, node: _Node) -> None:
        node.engagement = None
        self._set_state(node, NodeState.STANDBY)

    def _node(self, node_id: str) -> _Node:
        return next(n for n in self._nodes if n.id == node_id)

    def _track(self, track_id: str) -> _Track:
        return next(t for t in self._tracks if t.id == track_id)

    def _find_engagement(self, engagement_id: str) -> _Engagement | None:
        return next((e for e in self._engagements if e.id == engagement_id), None)

    # ------------------------------------------------------------------
    # Internals: world
    # ------------------------------------------------------------------

    def _advance_tracks(self, dt: float, world_dt: float) -> None:
        radius_m = self.config.site.protected_radius_km * 1000
        reached_m = self.config.timing.site_reached_km * 1000
        entered: list[str] = []
        for track in self._tracks:
            if track.status is not TrackStatus.INBOUND:
                continue
            track.report = track.source.advance(world_dt)
            track.since_breadcrumb += dt
            if track.since_breadcrumb >= self.config.track.trail_interval_s:
                track.trail.append(track.report.position)
                track.since_breadcrumb = 0.0

            distance = ground_distance_m(self._site, track.report.position)
            if not track.inside and distance <= radius_m:
                track.inside = True
                entered.append(track.id)
            if distance <= reached_m:
                self._reached_site(track)
        if entered:
            self._emit(f"{', '.join(entered)} entered the protected area")

    def _reached_site(self, track: _Track) -> None:
        track.status = TrackStatus.REACHED_SITE
        self._emit(f"{track.id} reached {self.config.site.site_id} - not intercepted")
        engagement = self._find_engagement(track.engagement_id) if track.engagement_id else None
        if engagement is not None and engagement.status in _ACTIVE:
            engagement.status = EngagementStatus.ABORTED
            self._stand_down(engagement)
            self._release(self._node(engagement.node_id))

    def _assign_nodes(self, dt: float) -> None:
        """Pair threats inside the protected area with their nearest free nodes, all at once.

        A wave does not cross the boundary on exactly the same tick, so pairing
        waits `assessment_delay_s` after the first crossing and then commits
        every pair together - the nearest node to each threat, closest pair
        first. Nodes of one wave therefore activate simultaneously.
        """
        waiting = [
            t
            for t in self._tracks
            if t.status is TrackStatus.INBOUND
            and t.inside
            and t.engagement_id is None
            and not t.declined
        ]
        free = [n for n in self._nodes if n.engagement is None and n.inventory > 0]
        if not waiting or not free:
            self._since_waiting = 0.0
            return
        self._since_waiting += dt
        if self._since_waiting < self.config.engagement.assessment_delay_s:
            return
        self._since_waiting = 0.0

        pairs = sorted(
            (ground_distance_m(n.position, t.report.position), n.id, t.id)
            for n in free
            for t in waiting
        )
        chosen: dict[str, str] = {}  # track id → node id
        used_nodes: set[str] = set()
        for _, node_id, track_id in pairs:
            if node_id in used_nodes or track_id in chosen:
                continue
            chosen[track_id] = node_id
            used_nodes.add(node_id)

        proposed = self.config.engagement.proposed_interceptors
        created: list[_Engagement] = []
        for track_id in sorted(chosen):
            node, track = self._node(chosen[track_id]), self._track(track_id)
            self._engagement_seq += 1
            engagement = _Engagement(
                id=f"R-{self._engagement_seq:02d}",
                node_id=node.id,
                track_id=track.id,
                proposed=min(proposed, node.inventory),
            )
            self._engagements.append(engagement)
            node.engagement = engagement
            track.engagement_id = engagement.id
            self._set_state(node, NodeState.TRACK_RECEIVED)
            self._aim(node, track)
            created.append(engagement)

        nodes = ", ".join(e.node_id for e in created)
        self._emit(f"{_plural(len(created), 'node')} activated - {nodes}")
        for engagement in created:
            self._emit(
                f"{engagement.id} proposed - {engagement.node_id} → {engagement.track_id}, "
                f"{_plural(engagement.proposed, 'interceptor')}"
            )

    def _aim(self, node: _Node, track: _Track) -> None:
        orientation = self.config.orientation
        position = track.report.position
        node.yaw.target = bearing_deg(node.position, position)
        line_of_sight = elevation_deg(
            ground_distance_m(node.position, position), track.report.altitude_m
        )
        node.pitch.target = min(
            orientation.max_elevation_deg,
            max(orientation.min_launch_elevation_deg, line_of_sight),
        )

    def _advance_node(self, node: _Node, dt: float) -> None:
        engagement = node.engagement
        if engagement is None:
            return
        track = self._track(engagement.track_id)
        if track.status is TrackStatus.INBOUND:
            self._aim(node, track)

        o = self.config.orientation
        if node.state in _SLEWING:
            slew_axis(
                node.yaw,
                dt,
                max_rate=o.yaw_max_rate_deg_s,
                accel=o.yaw_accel_deg_s2,
                gain=o.settle_gain_per_s,
                wrap=True,
            )
            slew_axis(
                node.pitch,
                dt,
                max_rate=o.pitch_max_rate_deg_s,
                accel=o.pitch_accel_deg_s2,
                gain=o.settle_gain_per_s,
                wrap=False,
            )

        misalignment = max(abs(node.yaw.error(wrap=True)), abs(node.pitch.error(wrap=False)))
        timing = self.config.engagement
        state = node.state
        if state is NodeState.TRACK_RECEIVED:
            if node.in_state >= timing.orient_delay_s:
                self._set_state(node, NodeState.ORIENTING)
        elif state is NodeState.ORIENTING:
            if misalignment <= o.ready_tolerance_deg:
                self._set_state(node, NodeState.READY)
                engagement.status = EngagementStatus.AWAITING_AUTHORIZATION
                self._emit(f"{node.id} ready - {engagement.id} awaiting operator authorization")
        elif state is NodeState.READY:
            if misalignment > o.realign_threshold_deg:
                self._set_state(node, NodeState.ORIENTING)
                engagement.status = EngagementStatus.PROPOSED
        elif state is NodeState.AUTHORIZED:
            if node.in_state >= timing.launch_delay_s:
                self._set_state(node, NodeState.SIMULATED_LAUNCH)
                engagement.status = EngagementStatus.IN_FLIGHT
                self._launch_due(node, engagement)
        elif state is NodeState.SIMULATED_LAUNCH:
            self._launch_due(node, engagement)

    def _launch_due(self, node: _Node, engagement: _Engagement) -> None:
        """Launch each pending interceptor once its slot in the salvo comes up."""
        interval = self.config.interceptor.salvo_interval_s
        capacity = self.config.nodes.inventory_capacity
        for index, interceptor in enumerate(engagement.interceptors):
            if (
                interceptor.status is InterceptorStatus.PENDING
                and node.in_state >= index * interval
            ):
                interceptor.status = InterceptorStatus.IN_FLIGHT
                node.inventory -= 1
                self._emit(
                    f"{interceptor.id} launched from {node.id} (simulated) - "
                    f"inventory {node.inventory}/{capacity}"
                )

    def _advance_interceptors(self, dt: float, world_dt: float) -> None:
        setup = self.config.interceptor
        travel = setup.speed_kmh / 3.6 * world_dt
        for engagement in self._engagements:
            if engagement.status is not EngagementStatus.IN_FLIGHT:
                continue
            track = self._track(engagement.track_id)
            target = track.report.position
            for interceptor in engagement.interceptors:
                if interceptor.status is not InterceptorStatus.IN_FLIGHT:
                    continue
                interceptor.flight_s += dt
                gap = ground_distance_m(interceptor.position, target)
                if gap - travel <= setup.intercept_radius_m:
                    interceptor.position = target
                    interceptor.trail.append(target)
                    interceptor.status = InterceptorStatus.INTERCEPT
                    self._resolve(engagement, interceptor, track)
                    break
                if interceptor.flight_s > setup.max_flight_s:
                    self.fail(f"{interceptor.id} did not reach {track.id}")
                    return
                # Display motion only: step the marker straight at the threat marker.
                interceptor.heading = bearing_deg(interceptor.position, target)
                interceptor.position = destination(
                    interceptor.position, interceptor.heading, travel
                )
                interceptor.since_breadcrumb += dt
                if interceptor.since_breadcrumb >= setup.trail_interval_s:
                    interceptor.trail.append(interceptor.position)
                    interceptor.since_breadcrumb = 0.0

    def _resolve(self, engagement: _Engagement, winner: _Interceptor, track: _Track) -> None:
        track.status = TrackStatus.INTERCEPTED
        engagement.status = EngagementStatus.INTERCEPTED
        engagement.intercept_point = winner.position
        self._stand_down(engagement)
        self._release(self._node(engagement.node_id))
        self._emit(f"Simulated intercept - {winner.id} reached {track.id}")

    def _stand_down(self, engagement: _Engagement) -> None:
        for interceptor in engagement.interceptors:
            if interceptor.status in (InterceptorStatus.PENDING, InterceptorStatus.IN_FLIGHT):
                interceptor.status = InterceptorStatus.STOOD_DOWN

    def _check_complete(self, dt: float) -> None:
        if any(t.status is TrackStatus.INBOUND for t in self._tracks):
            self._since_resolved = 0.0
            return
        self._since_resolved += dt
        if self._since_resolved < self.config.timing.complete_delay_s:
            return
        intercepted = sum(t.status is TrackStatus.INTERCEPTED for t in self._tracks)
        self.running = False
        self.state = MissionState.COMPLETE
        self._emit(
            f"Mission complete - {intercepted} of {_plural(len(self._tracks), 'threat')} "
            "intercepted (simulated)"
        )

    # ------------------------------------------------------------------
    # Internals: snapshot models
    # ------------------------------------------------------------------

    def _track_model(self, track: _Track) -> Track:
        report = track.report
        trail = [*track.trail]
        if trail[-1] != report.position:
            trail.append(report.position)
        return Track(
            id=report.track_id,
            latitude=round(report.position.lat, 6),
            longitude=round(report.position.lon, 6),
            altitude_m=report.altitude_m,
            heading_deg=round(report.heading_deg, 2),
            speed_kmh=report.speed_kmh,
            status=track.status,
            source=report.source,
            site_distance_km=round(ground_distance_m(self._site, report.position) / 1000, 2),
            inside_protected_area=track.inside,
            engagement_id=track.engagement_id,
            trail=[_geo(p) for p in trail],
        )

    def _engagement_model(self, engagement: _Engagement) -> Engagement:
        node = self._node(engagement.node_id)
        report = self._track(engagement.track_id).report
        range_m = ground_distance_m(node.position, report.position)
        return Engagement(
            id=engagement.id,
            node_id=engagement.node_id,
            track_id=engagement.track_id,
            status=engagement.status,
            proposed_interceptors=engagement.proposed,
            range_km=round(range_m / 1000, 2),
            bearing_deg=round(bearing_deg(node.position, report.position), 2),
            elevation_deg=round(elevation_deg(range_m, report.altitude_m), 2),
            interceptor_ids=[i.id for i in engagement.interceptors],
            intercept_point=_geo(engagement.intercept_point)
            if engagement.intercept_point
            else None,
        )

    def _interceptor_model(self, interceptor: _Interceptor) -> SimulatedInterceptor:
        trail = [*interceptor.trail]
        if trail[-1] != interceptor.position:
            trail.append(interceptor.position)
        return SimulatedInterceptor(
            id=interceptor.id,
            node_id=interceptor.node_id,
            track_id=interceptor.track_id,
            engagement_id=interceptor.engagement_id,
            latitude=round(interceptor.position.lat, 6),
            longitude=round(interceptor.position.lon, 6),
            heading_deg=round(interceptor.heading, 2),
            state=interceptor.status,
            trail=[_geo(p) for p in trail],
        )
