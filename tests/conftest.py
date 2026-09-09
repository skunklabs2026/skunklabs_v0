"""Shared test fixtures.

Everything here uses a controllable clock so that dwell-based transitions can
be exercised deterministically, without sleeping.
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.mission.rules import ClassRule, ConfidenceRule, DwellRule, RuleEngine
from backend.mission.state_machine import MissionConfig, MissionStateMachine
from backend.vision.detector import Detection
from backend.vision.tracker import Track


class FakeClock:
    """A manually advanced clock."""

    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += seconds
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def rule_engine() -> RuleEngine:
    return RuleEngine(
        [
            ClassRule(("uav",)),
            ConfidenceRule(0.60),
            DwellRule(2.0),
        ]
    )


@pytest.fixture
def mission_config() -> MissionConfig:
    return MissionConfig(
        confirmation_time=2.0,
        follow_time=1.5,
        target_lost_grace=1.0,
        target_lost_hold=2.5,
        actuated_hold=6.0,
        actuator_duration=1.6,
    )


@pytest.fixture
def machine(rule_engine, mission_config, clock) -> MissionStateMachine:
    return MissionStateMachine(rule_engine, mission_config, clock=clock)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient backed by the real pipeline over the demo clip.

    Uploads are redirected to a temp directory so tests never write into the
    repository's asset folder.
    """
    from fastapi.testclient import TestClient

    from backend.config.settings import get_settings

    video = Path(__file__).resolve().parents[1] / "assets" / "videos" / "demo_drone.mp4"
    if not video.exists():
        pytest.skip("demo clip not generated; run scripts/make_demo_video.py")

    library = tmp_path / "library"
    library.mkdir()

    get_settings.cache_clear()
    monkeypatch.setenv("SKUNK_VIDEO_PATH", str(video))
    monkeypatch.setenv("SKUNK_TARGET_FPS", "60")
    monkeypatch.setenv("SKUNK_VIDEO_LIBRARY_DIR", str(library))
    monkeypatch.setenv("SKUNK_UPLOAD_DIR", str(library / "uploads"))
    # Mission reports go to a temp directory so a test run never leaves
    # reports in the repository's `runs/`.
    monkeypatch.setenv("SKUNK_RUNS_DIR", str(tmp_path / "runs"))

    from backend.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def make_track(
    *,
    track_id: int = 1,
    first_seen: float = 1_000.0,
    confidence: float = 0.9,
    object_class: str = "uav",
    confirmed: bool = True,
    hits: int = 10,
) -> Track:
    """Build a Track in a chosen state, bypassing the tracker."""
    track = Track(
        track_id=track_id,
        x=100.0,
        y=100.0,
        width=40.0,
        height=30.0,
        confidence=confidence,
        object_class=object_class,
        first_seen=first_seen,
        last_seen=first_seen,
        hits=hits,
        confirmed=confirmed,
        trail=deque(maxlen=48),
    )
    track._confidence_history.append(confidence)
    return track


def make_detection(
    *,
    x: float = 100.0,
    y: float = 100.0,
    width: float = 40.0,
    height: float = 30.0,
    confidence: float = 0.9,
    object_class: str = "uav",
) -> Detection:
    return Detection(
        x=x,
        y=y,
        width=width,
        height=height,
        confidence=confidence,
        object_class=object_class,
    )
