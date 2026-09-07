"""API contract, actuator and end-to-end integration tests."""

from __future__ import annotations

import time

import pytest

from backend.actuation.simulated import SimulatedActuator
from backend.schemas import MissionState, TelemetryFrame


class TestSimulatedActuator:
    def test_fire_reports_success(self):
        actuator = SimulatedActuator()
        result = actuator.fire("UAV-001")
        assert result.ok
        assert result.actuator == "simulated"
        assert result.target_id == "UAV-001"

    def test_fire_is_counted(self):
        actuator = SimulatedActuator()
        actuator.fire("UAV-001")
        actuator.fire("UAV-002")
        assert actuator.fire_count == 2

    def test_detail_states_no_physical_action(self):
        """The safety posture must be explicit in the logged event."""
        result = SimulatedActuator().fire("UAV-001")
        assert "no physical action" in result.detail.lower()

    def test_handles_missing_target(self):
        assert SimulatedActuator().fire(None).ok


class TestSchemas:
    def test_telemetry_serialises_class_alias(self):
        """`object_class` must appear as `class` on the wire."""
        from backend.schemas import BBox, MissionStatus, SystemStatus, Target

        frame = TelemetryFrame(
            timestamp=time.time(),
            system=SystemStatus(
                sensor_online=True,
                detector="motion",
                detector_ready=True,
                video_source="file",
                fps=25.0,
                frame_index=1,
            ),
            mission=MissionStatus(state=MissionState.TRACKING, target_id="UAV-001"),
            targets=[
                Target(
                    target_id="UAV-001",
                    object_class="uav",
                    confidence=0.94,
                    bbox=BBox(x=0.1, y=0.1, width=0.2, height=0.2),
                    tracking=True,
                    age_frames=10,
                    track_duration=1.2,
                )
            ],
        )
        payload = frame.model_dump(mode="json", by_alias=True)
        assert payload["targets"][0]["class"] == "uav"
        assert payload["mission"]["state"] == "TRACKING"

    def test_bbox_rejects_out_of_range(self):
        from backend.schemas import BBox

        with pytest.raises(Exception):
            BBox(x=1.5, y=0.0, width=0.1, height=0.1)


class TestApi:
    def test_health(self, client):
        body = client.get("/api/health").json()
        assert body["ok"] is True
        assert body["detector"] in ("motion", "yolo")

    def test_telemetry_shape(self, client):
        # Give the pipeline a moment to produce a frame.
        for _ in range(40):
            response = client.get("/api/telemetry")
            if response.json():
                break
            time.sleep(0.1)

        body = response.json()
        assert body is not None
        assert "mission" in body and "system" in body and "targets" in body
        assert body["mission"]["state"] in {s.value for s in MissionState}

    def test_authorize_rejected_while_searching(self, client):
        """The HTTP surface enforces the same interlock as the state machine."""
        body = client.post("/api/authorize").json()
        assert body["ok"] is False
        assert "rejected" in body["detail"].lower()

    def test_reset_always_succeeds(self, client):
        body = client.post("/api/reset").json()
        assert body["ok"] is True
        assert body["state"] == MissionState.SEARCHING.value

    def test_events_endpoint(self, client):
        events = client.get("/api/events").json()
        assert isinstance(events, list)


class TestEndToEnd:
    def test_full_sequence_over_the_api(self, client):
        """Play the clip, wait for the gate, authorize, observe actuation."""
        deadline = time.time() + 45.0
        states: list[str] = []
        authorized = False

        while time.time() < deadline:
            telemetry = client.get("/api/telemetry").json()
            if not telemetry:
                time.sleep(0.05)
                continue

            state = telemetry["mission"]["state"]
            if not states or states[-1] != state:
                states.append(state)

            if telemetry["mission"]["can_authorize"] and not authorized:
                assert client.post("/api/authorize").json()["ok"] is True
                authorized = True

            if state == MissionState.ACTUATED.value:
                break
            time.sleep(0.05)

        assert authorized, f"never reached the authorization gate; saw {states}"
        assert MissionState.ACTUATED.value in states, f"never actuated; saw {states}"

        # Assert the ordering against the event log rather than the polled
        # snapshots: a short-lived state such as DETECTED can last a single
        # frame and be missed by any polling interval. The event log records
        # every transition, so it is the authoritative record.
        events = client.get("/api/events").json()
        transitions = [
            m.split(" -> ", 1)[1].split(":", 1)[0]
            for m in (e["message"] for e in events)
            if " -> " in m
        ]

        order = [
            MissionState.DETECTED.value,
            MissionState.TRACKING.value,
            MissionState.THREAT_CONFIRMED.value,
            MissionState.FOLLOWING.value,
            MissionState.AWAITING_AUTHORIZATION.value,
            MissionState.AUTHORIZED.value,
            MissionState.ACTUATED.value,
        ]
        missing = [s for s in order if s not in transitions]
        assert not missing, f"missing states {missing}; log was {transitions}"

        indices = [transitions.index(s) for s in order]
        assert indices == sorted(indices), f"states out of order: {transitions}"

    def test_websocket_pushes_telemetry(self, client):
        with client.websocket_connect("/ws/telemetry") as ws:
            history = ws.receive_json()
            assert history["type"] == "history"

            payload = ws.receive_json()
            assert payload["type"] == "telemetry"
            assert payload["mission"]["state"] in {s.value for s in MissionState}
            assert "sensor_online" in payload["system"]
