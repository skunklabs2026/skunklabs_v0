"""V0 defense scenario over HTTP and WebSocket, with the video pipeline off."""

from __future__ import annotations

import time

import pytest
from starlette.websockets import WebSocketDisconnect


def test_default_state_is_idle(scenario_client):
    body = scenario_client.get("/api/scenario").json()
    assert body["type"] == "scenario"
    assert body["state"] == "IDLE"
    assert body["site"]["protected_radius_km"] == 40.0
    assert body["site"]["location_source"] == "DEFAULT"
    assert [n["id"] for n in body["nodes"]] == [f"NODE-0{i}" for i in range(1, 7)]
    assert [s["id"] for s in body["scenarios"]] == ["S1", "S2", "S3"]
    assert body["can_start"] is True
    assert body["tracks"] == body["engagements"] == body["decision_queue"] == []


def test_configure_scenario_and_location(scenario_client):
    response = scenario_client.post(
        "/api/scenario/configure",
        json={"scenario_id": "S3", "latitude": 45.07, "longitude": 7.69},
    )
    assert response.status_code == 200
    snapshot = response.json()["snapshot"]
    assert snapshot["scenario_id"] == "S3"
    assert (snapshot["site"]["latitude"], snapshot["site"]["longitude"]) == (45.07, 7.69)
    assert snapshot["site"]["location_source"] == "DEVICE"


def test_configure_validation(scenario_client):
    assert scenario_client.post(
        "/api/scenario/configure", json={"latitude": 95, "longitude": 0}
    )
    bad = scenario_client.post("/api/scenario/configure", json={"latitude": 95, "longitude": 0})
    assert bad.status_code == 422
    unknown = scenario_client.post("/api/scenario/configure", json={"scenario_id": "S9"})
    assert unknown.status_code == 409 and "S9" in unknown.json()["detail"]


def test_start_locks_configuration_until_reset(scenario_client):
    scenario_client.post("/api/scenario/configure", json={"scenario_id": "S2"})
    started = scenario_client.post("/api/scenario/start").json()
    assert started["snapshot"]["state"] == "RUNNING"
    assert len(started["snapshot"]["tracks"]) == 6

    assert scenario_client.post("/api/scenario/start").status_code == 409
    locked = scenario_client.post("/api/scenario/configure", json={"scenario_id": "S1"})
    assert locked.status_code == 409

    reset = scenario_client.post("/api/scenario/reset").json()["snapshot"]
    assert reset["state"] == "IDLE" and reset["scenario_id"] == "S2"
    assert reset["tracks"] == [] and reset["events"] == []


@pytest.mark.parametrize("command", ["authorize", "decline"])
def test_decisions_on_an_unknown_response_are_409(scenario_client, command):
    response = scenario_client.post(f"/api/scenario/responses/R-99/{command}")
    assert response.status_code == 409
    assert response.json()["detail"] == "No response R-99."


def test_authorize_rejects_a_non_positive_count(scenario_client):
    response = scenario_client.post(
        "/api/scenario/responses/R-01/authorize", json={"interceptors": 0}
    )
    assert response.status_code == 422


def test_reassign_needs_a_node_and_an_existing_response(scenario_client):
    missing_body = scenario_client.post("/api/scenario/responses/R-01/reassign", json={})
    assert missing_body.status_code == 422

    unknown = scenario_client.post(
        "/api/scenario/responses/R-99/reassign", json={"node_id": "NODE-01"}
    )
    assert unknown.status_code == 409
    assert "R-99" in unknown.json()["detail"]


def test_settings_can_pin_the_site_location():
    """A demo can be centred anywhere without touching scenario config."""
    from backend.config.settings import Settings
    from backend.main import _scenario_config
    from backend.scenario.config import SiteSetup

    default = _scenario_config(Settings(_env_file=None))
    assert default.site.latitude == SiteSetup().latitude
    assert default.site.longitude == SiteSetup().longitude

    pinned = _scenario_config(
        Settings(
            _env_file=None,
            site_latitude=45.4642,
            site_longitude=9.19,
            site_name="Milan substation",
        )
    )
    assert (pinned.site.latitude, pinned.site.longitude) == (45.4642, 9.19)
    assert pinned.site.name == "Milan substation"

    # One coordinate on its own is not a position, so the default stands.
    half = _scenario_config(Settings(_env_file=None, site_latitude=45.4642))
    assert half.site.latitude == SiteSetup().latitude


def test_scenario_ticks_inside_the_running_app(scenario_client):
    """The lifespan's tick task advances the demo without any client polling it."""
    scenario_client.post("/api/scenario/start")
    deadline = time.time() + 5.0
    elapsed = 0.0
    while time.time() < deadline and elapsed < 0.5:
        time.sleep(0.1)
        elapsed = scenario_client.get("/api/scenario").json()["elapsed_s"]
    assert elapsed >= 0.5


def test_websocket_pushes_snapshots(scenario_client):
    scenario_client.post("/api/scenario/start")
    with scenario_client.websocket_connect("/ws/scenario") as ws:
        first = ws.receive_json()
        second = ws.receive_json()
    assert first["type"] == second["type"] == "scenario"
    assert second["elapsed_s"] >= first["elapsed_s"]
    assert second["revision"] >= first["revision"]


def test_health_without_the_video_pipeline(scenario_client):
    body = scenario_client.get("/api/health").json()
    assert body == {"ok": True, "mission_state": "IDLE", "video_pipeline": False}


def test_sensor_lab_routes_explain_that_the_pipeline_is_off(scenario_client):
    response = scenario_client.get("/api/telemetry")
    assert response.status_code == 503
    assert "SKUNK_VIDEO_PIPELINE_ENABLED" in response.json()["detail"]

    with (
        scenario_client.websocket_connect("/ws/telemetry") as ws,
        pytest.raises(WebSocketDisconnect),
    ):
        ws.receive_json()


@pytest.fixture
def built_client(tmp_path, monkeypatch):
    """The app serving a (fake) production frontend build."""
    from fastapi.testclient import TestClient

    from backend.config.settings import get_settings

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>console</title>")
    (dist / "assets" / "app.js").write_text("console.log('app')")

    get_settings.cache_clear()
    monkeypatch.setenv("SKUNK_FRONTEND_DIST", str(dist))
    from backend.main import create_app

    with TestClient(create_app()) as client:
        yield client
    get_settings.cache_clear()


@pytest.mark.parametrize("path", ["/", "/map", "/launcher", "/sensor-lab"])
def test_client_side_routes_serve_the_console(built_client, path):
    response = built_client.get(path)
    assert response.status_code == 200
    assert "<title>console</title>" in response.text


def test_real_files_and_unknown_paths(built_client):
    assert built_client.get("/assets/app.js").text == "console.log('app')"
    # A missing file must not come back as the HTML page.
    assert built_client.get("/models/skunk-launcher.glb").status_code == 404
    assert built_client.get("/api/does-not-exist").status_code == 404
