"""The canister subsystem model, the mission timeline and run recording."""

from __future__ import annotations

import json

import pytest

from backend.actuation.base import build_launch_command
from backend.canister.status import CanisterInputs, CanisterStatusModel
from backend.mission.recording import MissionRecorder
from backend.mission.timeline import PHASE_ORDER, build_timeline
from backend.schemas import (
    EventCode,
    EventKind,
    LaunchAcknowledgement,
    LauncherState,
    MissionEvent,
    MissionPhase,
    MissionState,
    PhaseStatus,
    ReadinessState,
    SubsystemId,
    SubsystemState,
)


def healthy(**overrides) -> CanisterInputs:
    base = dict(
        sensor_online=True,
        detector_ready=True,
        detector_name="motion",
        tracker_ready=True,
        fps=25.0,
        target_fps=25.0,
    )
    base.update(overrides)
    return CanisterInputs(**base)


class TestCanisterStatus:
    @pytest.fixture
    def model(self) -> CanisterStatusModel:
        return CanisterStatusModel(canister_id="CANISTER 01")

    def test_healthy_canister_is_operational(self, model):
        status = model.build(healthy())
        assert status.state is SubsystemState.OPERATIONAL
        assert status.canister_id == "CANISTER 01"

    def test_every_subsystem_is_reported(self, model):
        reported = {s.id for s in model.build(healthy()).subsystems}
        assert reported == set(SubsystemId)

    def test_offline_sensor_takes_the_canister_offline(self, model):
        status = model.build(healthy(sensor_online=False))
        assert status.state is SubsystemState.OFFLINE
        assert "Sensor" in status.detail

    def test_slow_pipeline_is_degraded_not_offline(self, model):
        status = model.build(healthy(fps=5.0, target_fps=25.0))
        assert status.state is SubsystemState.DEGRADED

    def test_starting_pipeline_is_initialising_not_degraded(self, model):
        """A canister two seconds after power-on must not cry wolf."""
        status = model.build(healthy(detector_ready=False, fps=0.0))
        assert status.state is SubsystemState.INITIALISING

    def test_unmeasured_subsystems_say_so(self, model):
        """No power rail and no thermistor exist - the panel must not invent them."""
        by_id = {s.id: s for s in model.build(healthy()).subsystems}

        power = by_id[SubsystemId.POWER]
        assert power.state is SubsystemState.NOT_CONNECTED
        assert power.measured is False

        temperature = by_id[SubsystemId.TEMPERATURE]
        assert temperature.state is SubsystemState.NOT_AVAILABLE
        assert temperature.measured is False

    def test_absent_sensors_do_not_degrade_the_headline(self, model):
        """Power and temperature are unknown on every V0 build, always.

        If they counted against the roll-up, the canister would read DEGRADED
        permanently and the headline would stop meaning anything.
        """
        assert model.build(healthy()).state is SubsystemState.OPERATIONAL

    def test_launcher_is_reported_as_simulated(self, model):
        launcher = next(
            s for s in model.build(healthy()).subsystems if s.id is SubsystemId.LAUNCHER
        )
        assert launcher.state is SubsystemState.SAFE
        assert "simulated" in launcher.detail.lower()
        assert launcher.measured is False

    def test_acknowledged_launcher_is_armed_but_nominal(self, model):
        launcher = next(
            s
            for s in model.build(healthy(launcher_state=LauncherState.ACKNOWLEDGED)).subsystems
            if s.id is SubsystemId.LAUNCHER
        )
        assert launcher.state is SubsystemState.ARMED
        assert launcher.nominal is True

    def test_launcher_fault_degrades_the_canister(self, model):
        status = model.build(healthy(launcher_state=LauncherState.FAULT))
        assert status.state is SubsystemState.DEGRADED


class TestMissionTimeline:
    def test_seven_phases_always(self):
        for state in MissionState:
            assert len(build_timeline(state, 0.0)) == len(PHASE_ORDER) == 7

    def test_searching_is_the_first_active_phase(self):
        steps = build_timeline(MissionState.SEARCHING, 0.0)
        assert steps[0].phase is MissionPhase.SEARCH
        assert steps[0].status is PhaseStatus.ACTIVE
        assert all(s.status is PhaseStatus.PENDING for s in steps[1:])

    def test_earlier_phases_complete(self):
        steps = build_timeline(MissionState.FOLLOWING, 0.5)
        by_phase = {s.phase: s for s in steps}
        assert by_phase[MissionPhase.FOLLOW].status is PhaseStatus.ACTIVE
        for phase in (MissionPhase.SEARCH, MissionPhase.DETECT, MissionPhase.TRACK):
            assert by_phase[phase].status is PhaseStatus.COMPLETE
        assert by_phase[MissionPhase.LAUNCH].status is PhaseStatus.PENDING

    def test_actuated_completes_the_whole_timeline(self):
        steps = build_timeline(MissionState.ACTUATED, 1.0)
        assert all(s.status is PhaseStatus.COMPLETE for s in steps)

    def test_target_lost_rewinds_to_search(self):
        """A lost target is a setback, not a step - the timeline must not lie."""
        steps = build_timeline(MissionState.TARGET_LOST, 0.0)
        assert steps[0].status is PhaseStatus.ACTIVE
        assert all(s.status is PhaseStatus.PENDING for s in steps[1:])

    def test_progress_applies_to_the_active_phase_only(self):
        steps = build_timeline(MissionState.TRACKING, 0.4)
        active = next(s for s in steps if s.status is PhaseStatus.ACTIVE)
        assert active.progress == pytest.approx(0.4)
        assert all(s.progress == 0.0 for s in steps if s.status is PhaseStatus.PENDING)

    def test_progress_is_clamped(self):
        steps = build_timeline(MissionState.TRACKING, 4.0)
        assert next(s for s in steps if s.status is PhaseStatus.ACTIVE).progress == 1.0


class TestMissionRecording:
    @pytest.fixture
    def recorder(self, tmp_path) -> MissionRecorder:
        return MissionRecorder(tmp_path / "runs")

    def test_report_is_written_on_finish(self, recorder, tmp_path):
        recorder.start(source="demo.mp4", detector="motion", now=1_000.0)
        path = recorder.finish(now=1_010.0)
        assert path is not None and path.exists()

        report = json.loads(path.read_text())
        assert report["source"] == "demo.mp4"
        assert report["duration_s"] == pytest.approx(10.0)

    def test_mission_ids_are_sequential_within_a_day(self, recorder):
        recorder.start(source="a.mp4", detector="motion", now=1_000.0)
        first = recorder.run.mission_id
        recorder.finish(now=1_001.0)

        recorder.start(source="b.mp4", detector="motion", now=1_002.0)
        second = recorder.run.mission_id
        recorder.finish(now=1_003.0)

        assert first.endswith("_001")
        assert second.endswith("_002")

    def test_full_engagement_is_captured(self, recorder):
        recorder.start(source="demo.mp4", detector="motion", now=1_000.0)

        for code, kind in (
            (EventCode.OBJECT_DETECTED, EventKind.DETECTION),
            (EventCode.TRACK_CREATED, EventKind.TRACK),
            (EventCode.TRACK_CONFIRMED, EventKind.TRACK),
            (EventCode.ENGAGEMENT_READY, EventKind.STATE),
        ):
            recorder.record_event(
                MissionEvent(
                    timestamp=1_001.0,
                    kind=kind,
                    message=code.value,
                    code=code,
                    target_id="UAV-001",
                )
            )

        recorder.record_transition(MissionState.AUTHORIZED, "UAV-001", 1_005.0)
        recorder.record_authorization(ReadinessState.READY_FOR_AUTHORIZATION, 1_005.0)

        command = build_launch_command(
            target_id="UAV-001",
            mission_state=MissionState.AUTHORIZED,
            readiness=ReadinessState.AUTHORIZED,
            authorized_at=1_005.0,
        )
        recorder.record_launch(
            command,
            LaunchAcknowledgement(
                command_id=command.command_id,
                actuator="simulated",
                accepted=True,
                acknowledged_at=1_005.1,
                latency_ms=12.0,
            ),
        )

        path = recorder.finish(now=1_010.0)
        report = json.loads(path.read_text())

        assert report["summary"]["primary_target"] == "UAV-001"
        assert report["summary"]["tracks_created"] == 1
        assert report["summary"]["launch_acknowledged"] is True
        assert report["summary"]["acknowledgement_latency_ms"] == 12.0
        assert report["launch_command"]["command_id"] == command.command_id
        assert report["authorization"]["readiness_state"] == "READY_FOR_AUTHORIZATION"
        assert next(e["code"] for e in report["events"]) == "OBJECT_DETECTED"

    def test_per_frame_chatter_is_not_recorded(self, recorder):
        """A report nobody reads is not a record."""
        recorder.start(source="demo.mp4", detector="motion", now=1_000.0)
        recorder.record_event(
            MissionEvent(
                timestamp=1_001.0,
                kind=EventKind.INFO,
                message="frame",
                code=EventCode.SYSTEM_INFO,
            )
        )
        assert recorder.run.events == []

    def test_disabled_recorder_writes_nothing(self, tmp_path):
        recorder = MissionRecorder(tmp_path / "runs", enabled=False)
        assert recorder.start(source="a.mp4", detector="motion") is None
        assert recorder.finish() is None
        assert not (tmp_path / "runs").exists()

    def test_recording_after_finish_is_ignored(self, recorder):
        """The recorder must never fail a run because no report is open."""
        recorder.record_transition(MissionState.SEARCHING, None, 1_000.0)
        recorder.record_authorization(ReadinessState.AUTHORIZED, 1_000.0)
        recorder.record_frame_stats(frames=1, detections_total=0, fps=25.0, inference_ms=1.0)
