"""V0 defense scenario: layout, threat scenarios, node activation, the decision flow.

Driven with a fixed step and a frozen timestamp, so whole missions replay
deterministically in well under a second each.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from backend.scenario.config import InterceptorSetup, NodeSetup, ScenarioConfig, SiteSetup
from backend.scenario.geo import LatLon, bearing_deg, ground_distance_m, shortest_delta
from backend.scenario.models import (
    EngagementStatus,
    InterceptorStatus,
    LocationSource,
    MissionState,
    NodeState,
    TrackStatus,
)
from backend.scenario.service import ScenarioService
from backend.scenario.simulation import MAX_STEP_S, DefenseScenario, _Axis, slew_axis

DT = 1 / 20
NOW = 1_700_000_000.0
SITE = LatLon(SiteSetup().latitude, SiteSetup().longitude)
AWAITING = EngagementStatus.AWAITING_AUTHORIZATION


def make(config: ScenarioConfig | None = None, *, scenario: str = "S1") -> DefenseScenario:
    s = DefenseScenario(config, clock=lambda: NOW)
    assert s.configure(scenario_id=scenario).ok
    return s


def run_until(s: DefenseScenario, predicate, max_s: float = 120.0) -> float:
    elapsed = 0.0
    while elapsed < max_s:
        if predicate(s):
            return elapsed
        s.step(DT)
        elapsed += DT
    raise AssertionError(f"not reached within {max_s}s; state={s.state.value}")


def by_id(items, item_id):
    return next(item for item in items if item.id == item_id)


def activated(s: DefenseScenario) -> DefenseScenario:
    """Start, and run until the first responses have been proposed."""
    s.start()
    run_until(s, lambda x: x.snapshot().engagements)
    return s


def all_awaiting(s: DefenseScenario) -> DefenseScenario:
    activated(s)
    run_until(s, lambda x: all(e.status is AWAITING for e in x.snapshot().engagements))
    return s


def authorize_everything(s: DefenseScenario) -> DefenseScenario:
    """Run a mission, authorizing each response as soon as it awaits a decision."""
    s.start()
    while s.running:
        for engagement in s.snapshot().engagements:
            if engagement.status is AWAITING:
                assert s.authorize(engagement.id).ok
        s.step(DT)
    return s


class TestLayout:
    def test_six_nodes_evenly_on_a_ring_facing_outward(self):
        nodes = make().snapshot().nodes
        assert [n.id for n in nodes] == [f"NODE-0{i}" for i in range(1, 7)]
        for index, node in enumerate(nodes):
            position = LatLon(node.latitude, node.longitude)
            assert ground_distance_m(SITE, position) == pytest.approx(20_000, abs=1)
            assert shortest_delta(bearing_deg(SITE, position), 60 * index) == pytest.approx(
                0, abs=0.01
            )
            assert shortest_delta(node.current_yaw_deg, 60 * index) == pytest.approx(
                0, abs=0.01
            )
            assert node.state is NodeState.STANDBY
            assert (node.inventory, node.inventory_capacity) == (6, 6)
            assert node.coverage_radius_km == 25.0

    def test_protected_site_and_scenarios(self):
        snap = make().snapshot()
        assert snap.site.protected_radius_km == 40.0
        assert snap.site.location_source is LocationSource.DEFAULT
        assert [(o.id, o.threat_count) for o in snap.scenarios] == [
            ("S1", 4),
            ("S2", 6),
            ("S3", 6),
        ]
        assert snap.state is MissionState.IDLE
        assert snap.can_start and snap.can_configure
        assert snap.tracks == snap.engagements == snap.decision_queue == []


class TestConfigure:
    def test_selects_a_scenario(self):
        assert make(scenario="S2").snapshot().scenario_id == "S2"

    def test_unknown_scenario_rejected(self):
        outcome = make().configure(scenario_id="S9")
        assert outcome.ok is False and "S1, S2, S3" in outcome.detail

    def test_device_location_recentres_the_site_and_nodes(self):
        s = make()
        assert s.configure(latitude=45.07, longitude=7.69).ok
        snap = s.snapshot()
        centre = LatLon(45.07, 7.69)
        assert (snap.site.latitude, snap.site.longitude) == (45.07, 7.69)
        assert snap.site.location_source is LocationSource.DEVICE
        for node in snap.nodes:
            distance = ground_distance_m(centre, LatLon(node.latitude, node.longitude))
            assert distance == pytest.approx(20_000, abs=1)

    def test_half_a_location_is_rejected(self):
        assert make().configure(latitude=45.0).ok is False

    def test_locked_while_running_and_kept_through_reset(self):
        s = make(scenario="S3")
        s.configure(latitude=45.07, longitude=7.69)
        s.start()
        assert s.configure(scenario_id="S1").ok is False
        s.reset()
        snap = s.snapshot()
        assert snap.scenario_id == "S3" and snap.site.latitude == 45.07
        assert s.configure(scenario_id="S1").ok


class TestScenarios:
    @pytest.mark.parametrize(
        ("scenario", "groups"),
        [
            ("S1", {90.0: 4}),
            ("S2", {90.0: 3, 270.0: 3}),
            ("S3", {0.0: 4, 135.0: 2}),
        ],
    )
    def test_threats_come_from_the_scenario_directions(self, scenario, groups):
        s = make(scenario=scenario)
        s.start()
        tracks = s.snapshot().tracks
        spawn_range = s.config.track.spawn_range_km
        counts = dict.fromkeys(groups, 0)
        for track in tracks:
            position = LatLon(track.latitude, track.longitude)
            direction = bearing_deg(SITE, position)
            group = next(g for g in groups if abs(shortest_delta(direction, g)) <= 20)
            counts[group] += 1
            assert track.site_distance_km == pytest.approx(spawn_range, abs=0.01)
            assert track.inside_protected_area is False
            assert shortest_delta(track.heading_deg, bearing_deg(position, SITE)) == (
                pytest.approx(0, abs=0.5)
            )
        assert counts == groups
        assert [t.id for t in tracks] == [f"T-{i:03d}" for i in range(1, len(tracks) + 1)]

    def test_a_group_crosses_into_the_area_together(self):
        """Within a fraction of a second - they are abreast at the same range."""
        s = make(scenario="S2")
        s.start()
        crossing = run_until(
            s, lambda x: any(t.inside_protected_area for t in x.snapshot().tracks)
        )
        run_until(s, lambda x: all(t.inside_protected_area for t in x.snapshot().tracks))
        assert s.snapshot().elapsed_s - crossing < 0.5


class TestActivation:
    def test_nothing_activates_outside_the_protected_area(self):
        s = make()
        s.start()
        run_until(s, lambda x: x.snapshot().elapsed_s >= 5.0)
        snap = s.snapshot()
        assert snap.engagements == []
        assert {n.state for n in snap.nodes} == {NodeState.STANDBY}

    def test_nearest_nodes_activate_together(self):
        snap = activated(make()).snapshot()
        pairs = {e.node_id: e.track_id for e in snap.engagements}
        # Threats fan out from 78° to 102°: the 60° and 120° nodes take the
        # outer pair, the 0° and 180° nodes the inner pair.
        assert pairs == {
            "NODE-02": "T-001",
            "NODE-01": "T-002",
            "NODE-04": "T-003",
            "NODE-03": "T-004",
        }
        states = {n.id: n.state for n in snap.nodes}
        assert {states[node] for node in pairs} == {NodeState.TRACK_RECEIVED}
        assert states["NODE-05"] is states["NODE-06"] is NodeState.STANDBY
        assert any(e.message.startswith("4 nodes activated") for e in snap.events)

    @pytest.mark.parametrize("scenario", ["S2", "S3"])
    def test_every_threat_gets_its_own_node(self, scenario):
        snap = activated(make(scenario=scenario)).snapshot()
        assert len(snap.engagements) == 6
        assert len({e.node_id for e in snap.engagements}) == 6

    def test_responses_are_proposed_in_threat_order(self):
        snap = activated(make()).snapshot()
        assert [(e.id, e.track_id) for e in snap.engagements] == [
            ("R-01", "T-001"),
            ("R-02", "T-002"),
            ("R-03", "T-003"),
            ("R-04", "T-004"),
        ]
        assert snap.decision_queue == ["R-01", "R-02", "R-03", "R-04"]
        assert {e.proposed_interceptors for e in snap.engagements} == {2}
        assert {e.status for e in snap.engagements} == {EngagementStatus.PROPOSED}

    def test_activated_nodes_orient_toward_their_threats(self):
        snap = all_awaiting(make()).snapshot()
        tolerance = make().config.orientation.ready_tolerance_deg
        for engagement in snap.engagements:
            node = by_id(snap.nodes, engagement.node_id)
            assert node.state is NodeState.READY
            error = abs(shortest_delta(node.current_yaw_deg, engagement.bearing_deg))
            assert error <= tolerance + 0.1

    def test_a_node_tracking_a_closing_threat_stays_ready(self):
        """The standing lag of tracking must not strand a node out of READY."""
        s = all_awaiting(make())
        run_until(s, lambda x: x.snapshot().tracks[0].site_distance_km <= 12.0)
        snap = s.snapshot()
        assert {by_id(snap.nodes, e.node_id).state for e in snap.engagements} == {
            NodeState.READY
        }
        assert snap.decision_queue == ["R-01", "R-02", "R-03", "R-04"]


class TestDecisionFlow:
    def test_cannot_authorize_while_the_node_is_orienting(self):
        s = activated(make())
        outcome = s.authorize("R-01")
        assert outcome.ok is False and "not AWAITING_AUTHORIZATION" in outcome.detail

    def test_each_response_is_authorized_individually(self):
        s = all_awaiting(make())
        assert s.authorize("R-02").ok
        snap = s.snapshot()
        r02 = by_id(snap.engagements, "R-02")
        assert r02.status is EngagementStatus.AUTHORIZED
        assert r02.interceptor_ids == ["INT-001", "INT-002"]
        assert by_id(snap.nodes, r02.node_id).state is NodeState.AUTHORIZED
        others = [e for e in snap.engagements if e.id != "R-02"]
        assert {e.status for e in others} == {AWAITING}
        assert snap.decision_queue == ["R-01", "R-03", "R-04"]

    def test_operator_can_change_the_interceptor_count(self):
        s = all_awaiting(make())
        assert s.authorize("R-01", 3).ok
        assert len(by_id(s.snapshot().engagements, "R-01").interceptor_ids) == 3

    @pytest.mark.parametrize(
        ("count", "reason"),
        [(0, "at least one interceptor"), (7, "only 6 interceptors available at NODE-02")],
    )
    def test_rejects_an_impossible_count(self, count, reason):
        s = all_awaiting(make())
        outcome = s.authorize("R-01", count)
        assert outcome.ok is False and reason in outcome.detail
        assert by_id(s.snapshot().engagements, "R-01").status is AWAITING

    def test_interceptor_ids_are_unique_across_responses(self):
        s = all_awaiting(make())
        s.authorize("R-01")
        s.authorize("R-02")
        assert [i.id for i in s.snapshot().interceptors] == [
            "INT-001",
            "INT-002",
            "INT-003",
            "INT-004",
        ]

    def test_decline_releases_the_node_and_the_threat_is_not_reproposed(self):
        s = all_awaiting(make())
        assert s.decline("R-01").ok
        run_until(s, lambda x: x.snapshot().elapsed_s >= 15.0)
        snap = s.snapshot()
        assert by_id(snap.engagements, "R-01").status is EngagementStatus.DECLINED
        node = by_id(snap.nodes, "NODE-02")
        assert node.state is NodeState.STANDBY and node.engagement_id is None
        assert "R-01" not in snap.decision_queue
        assert [e.id for e in snap.engagements if e.track_id == "T-001"] == ["R-01"]

    def test_decline_is_rejected_once_authorized(self):
        s = all_awaiting(make())
        s.authorize("R-01")
        outcome = s.decline("R-01")
        assert outcome.ok is False and "only a proposed response" in outcome.detail

    def test_unknown_response(self):
        s = all_awaiting(make())
        assert s.authorize("R-99").detail == "No response R-99."
        assert s.decline("R-99").detail == "No response R-99."

    def test_the_operator_can_hand_a_response_to_a_node_of_their_choosing(self):
        s = all_awaiting(make())
        snap = s.snapshot()
        original = by_id(snap.engagements, "R-01").node_id
        free = next(n.id for n in snap.nodes if n.engagement_id is None)

        assert s.reassign("R-01", free).ok
        snap = s.snapshot()
        assert by_id(snap.engagements, "R-01").node_id == free
        assert by_id(snap.nodes, free).engagement_id == "R-01"
        assert by_id(snap.nodes, free).state is NodeState.TRACK_RECEIVED
        released = by_id(snap.nodes, original)
        assert released.state is NodeState.STANDBY and released.engagement_id is None
        assert "reassigned by operator" in snap.events[-1].message

        # The chosen node orients from where it was, then can be authorized.
        run_until(
            s,
            lambda x: by_id(x.snapshot().engagements, "R-01").status
            is EngagementStatus.AWAITING_AUTHORIZATION,
        )
        assert s.authorize("R-01").ok
        assert by_id(s.snapshot().nodes, free).state is NodeState.AUTHORIZED

    def test_reassign_rejects_a_node_that_cannot_take_the_response(self):
        s = all_awaiting(make())
        snap = s.snapshot()
        assigned = by_id(snap.engagements, "R-01").node_id
        busy = by_id(snap.engagements, "R-02").node_id
        free = next(n.id for n in snap.nodes if n.engagement_id is None)

        assert s.reassign("R-99", free).detail == "No response R-99."
        assert s.reassign("R-01", "NODE-99").detail == "No node NODE-99."
        assert "already assigned" in s.reassign("R-01", assigned).detail
        assert "already answering" in s.reassign("R-01", busy).detail

        # An empty node cannot answer anything.
        next(n for n in s._nodes if n.id == free).inventory = 0
        assert "no interceptors left" in s.reassign("R-01", free).detail

    def test_reassign_is_rejected_once_authorized(self):
        s = all_awaiting(make())
        free = next(n.id for n in s.snapshot().nodes if n.engagement_id is None)
        s.authorize("R-01")
        outcome = s.reassign("R-01", free)
        assert outcome.ok is False and "only a proposed response" in outcome.detail

    def test_a_free_node_takes_a_waiting_threat(self):
        config = replace(ScenarioConfig(), nodes=NodeSetup(count=1))
        s = activated(make(config))
        assert [e.id for e in s.snapshot().engagements] == ["R-01"]
        s.decline("R-01")
        run_until(s, lambda x: len(x.snapshot().engagements) == 2, max_s=2.0)
        snap = s.snapshot()
        assert [e.id for e in snap.engagements] == ["R-01", "R-02"]
        assert by_id(snap.engagements, "R-02").node_id == "NODE-01"


class TestSimulatedIntercepts:
    def test_authorized_node_launches_a_salvo_and_draws_down_inventory(self):
        s = all_awaiting(make())
        s.authorize("R-01")
        run_until(s, lambda x: by_id(x.snapshot().nodes, "NODE-02").inventory == 5)
        snap = s.snapshot()
        assert by_id(snap.nodes, "NODE-02").state is NodeState.SIMULATED_LAUNCH
        assert by_id(snap.engagements, "R-01").status is EngagementStatus.IN_FLIGHT
        assert [i.state for i in snap.interceptors] == [
            InterceptorStatus.IN_FLIGHT,
            InterceptorStatus.PENDING,
        ]
        interval = s.config.interceptor.salvo_interval_s
        run_until(
            s, lambda x: by_id(x.snapshot().nodes, "NODE-02").inventory == 4, interval + DT
        )

    @pytest.mark.parametrize("scenario", ["S1", "S2", "S3"])
    def test_authorizing_every_response_intercepts_every_threat(self, scenario):
        snap = authorize_everything(make(scenario=scenario)).snapshot()
        assert snap.state is MissionState.COMPLETE and snap.running is False
        assert {t.status for t in snap.tracks} == {TrackStatus.INTERCEPTED}
        for engagement in snap.engagements:
            assert engagement.status is EngagementStatus.INTERCEPTED
            assert engagement.intercept_point is not None
            winners = [
                i
                for i in snap.interceptors
                if i.engagement_id == engagement.id and i.state is InterceptorStatus.INTERCEPT
            ]
            assert len(winners) == 1
        assert {n.state for n in snap.nodes} == {NodeState.STANDBY}
        total = len(snap.tracks)
        assert snap.events[-1].message.startswith(
            f"Mission complete - {total} of {total} threats"
        )

    def test_unlaunched_interceptors_stand_down_and_stay_in_inventory(self):
        config = replace(ScenarioConfig(), interceptor=InterceptorSetup(salvo_interval_s=100.0))
        s = all_awaiting(make(config))
        s.authorize("R-01")
        run_until(
            s,
            lambda x: by_id(x.snapshot().engagements, "R-01").status
            is EngagementStatus.INTERCEPTED,
        )
        snap = s.snapshot()
        assert [i.state for i in snap.interceptors] == [
            InterceptorStatus.INTERCEPT,
            InterceptorStatus.STOOD_DOWN,
        ]
        assert by_id(snap.nodes, "NODE-02").inventory == 5

    def test_interceptor_that_never_arrives_faults(self):
        config = replace(
            ScenarioConfig(), interceptor=InterceptorSetup(speed_kmh=1.0, max_flight_s=2.0)
        )
        s = all_awaiting(make(config))
        s.authorize("R-01")
        run_until(s, lambda x: x.state is MissionState.FAULT)
        snap = s.snapshot()
        assert snap.running is False
        assert "INT-001 did not reach T-001" in snap.fault
        assert s.step(DT) is False


class TestNoEngagement:
    def test_unanswered_threats_reach_the_site(self):
        s = make()
        s.start()
        run_until(s, lambda x: x.state is MissionState.COMPLETE)
        snap = s.snapshot()
        assert {t.status for t in snap.tracks} == {TrackStatus.REACHED_SITE}
        assert {e.status for e in snap.engagements} == {EngagementStatus.ABORTED}
        assert {n.state for n in snap.nodes} == {NodeState.STANDBY}
        assert {n.inventory for n in snap.nodes} == {6}
        assert snap.decision_queue == []
        assert snap.events[-1].message.startswith("Mission complete - 0 of 4 threats")

    def test_threat_reaching_the_site_stands_down_its_interceptors(self):
        # Slow enough that the threat arrives first, patient enough not to fault.
        config = replace(
            ScenarioConfig(), interceptor=InterceptorSetup(speed_kmh=5.0, max_flight_s=300.0)
        )
        s = all_awaiting(make(config))
        s.authorize("R-01")
        run_until(
            s, lambda x: by_id(x.snapshot().tracks, "T-001").status is not TrackStatus.INBOUND
        )
        snap = s.snapshot()
        assert by_id(snap.tracks, "T-001").status is TrackStatus.REACHED_SITE
        assert by_id(snap.engagements, "R-01").status is EngagementStatus.ABORTED
        assert {i.state for i in snap.interceptors} == {InterceptorStatus.STOOD_DOWN}


class TestReset:
    def test_reset_restores_the_configured_start(self):
        s = make(scenario="S2")
        s.configure(latitude=45.07, longitude=7.69)
        pristine = s.snapshot()
        authorize_everything(s)
        assert s.reset().ok
        assert s.snapshot() == pristine


class TestStepping:
    def test_large_steps_are_clamped(self):
        s = make()
        s.start()
        s.step(10.0)
        assert s.snapshot().elapsed_s == pytest.approx(MAX_STEP_S)

    def test_idle_step_changes_nothing(self):
        s = make()
        before = s.snapshot()
        assert s.step(DT) is False
        assert s.snapshot() == before

    def test_yaw_takes_the_short_way_through_north(self):
        axis = _Axis(position=350.0, target=10.0)
        positions = []
        for _ in range(200):
            slew_axis(axis, DT, max_rate=24, accel=60, gain=2.5, wrap=True)
            positions.append(axis.position)
        assert all(p >= 349.9 or p <= 10.0 for p in positions)
        assert axis.position == pytest.approx(10.0)
        assert axis.rate == 0.0

    def test_slew_never_overshoots(self):
        axis = _Axis(position=0.0, target=12.0)
        for _ in range(300):
            slew_axis(axis, DT, max_rate=10, accel=30, gain=2.5, wrap=False)
            assert 0.0 <= axis.position <= 12.0
        assert axis.position == 12.0


class TestService:
    def test_commands_publish_a_new_snapshot(self):
        async def scenario_run():
            service = ScenarioService(make())
            version, _ = await service.wait_for_update(-1, 0.01)
            result = await service.start()
            assert result.ok and result.snapshot.running
            new_version, snap = await service.wait_for_update(version, 0.01)
            assert new_version == version + 1
            assert snap == service.snapshot == result.snapshot
            assert snap.revision == new_version

        asyncio.run(scenario_run())

    def test_commands_pass_their_arguments_through(self):
        async def scenario_run():
            service = ScenarioService(make())
            configured = await service.configure(scenario_id="S3", latitude=45.0, longitude=7.0)
            assert configured.snapshot.scenario_id == "S3"
            all_awaiting(service.scenario)
            authorized = await service.authorize("R-01", 3)
            assert len(authorized.snapshot.engagements[0].interceptor_ids) == 3
            declined = await service.decline("R-02")
            assert declined.snapshot.engagements[1].status is EngagementStatus.DECLINED

        asyncio.run(scenario_run())

    def test_idle_tick_publishes_nothing_and_wait_times_out(self):
        async def scenario_run():
            service = ScenarioService(make())
            version, _ = await service.wait_for_update(-1, 0.01)
            await service.tick(DT)
            assert (await service.wait_for_update(version, 0.01))[0] == version

        asyncio.run(scenario_run())

    def test_rejected_command_reports_detail(self):
        async def scenario_run():
            result = await ScenarioService(make()).authorize("R-01")
            assert result.ok is False and result.detail == "No response R-01."

        asyncio.run(scenario_run())

    def test_step_exception_becomes_a_visible_fault(self, monkeypatch):
        async def scenario_run():
            scenario = make()
            service = ScenarioService(scenario)
            await service.start()

            def explode(_dt):
                raise RuntimeError("boom")

            monkeypatch.setattr(scenario, "step", explode)
            await service.tick(DT)
            assert service.snapshot.state is MissionState.FAULT
            assert "simulation error" in service.snapshot.fault

        asyncio.run(scenario_run())

    def test_run_loop_ticks_until_cancelled(self):
        async def scenario_run():
            service = ScenarioService(make())
            await service.start()
            task = asyncio.create_task(service.run())
            await asyncio.sleep(0.2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert service.snapshot.elapsed_s > 0

        asyncio.run(scenario_run())
