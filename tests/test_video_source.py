"""Video ingestion.

Both implementations promise the same thing: `read()` is safe to call after a
failure, and problems surface through `online` rather than as exceptions into
the pipeline loop. These tests hold them to that, using a fake capture rather
than a real file or camera so the failure paths are reachable at all.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from backend.video.source import (
    CameraVideoSource,
    FileVideoSource,
    _resize_to_width,
    build_video_source,
)


class FakeCapture:
    """Stands in for cv2.VideoCapture.

    `frames` is the sequence returned by successive reads; once exhausted,
    reads fail, which is how a real capture reports end-of-file.
    """

    def __init__(self, frames: list[np.ndarray] | None = None, *, opened: bool = True):
        self._frames = list(frames or [])
        self._opened = opened
        self.released = False
        self.position_resets = 0
        self.props: dict[int, float] = {}

    # Name matches the cv2 API this stands in for.
    def isOpened(self) -> bool:
        return self._opened

    def read(self):
        if not self._frames:
            return False, None
        return True, self._frames.pop(0)

    def set(self, prop: int, value: float) -> bool:
        if prop == cv2.CAP_PROP_POS_FRAMES and value == 0:
            self.position_resets += 1
            # A rewind makes the clip readable again.
            self._frames = [np.zeros((4, 4, 3), dtype=np.uint8)]
        self.props[prop] = value
        return True

    def get(self, prop: int) -> float:
        return self.props.get(prop, 0.0)

    def release(self) -> None:
        self.released = True
        self._opened = False


def frame(width: int = 8, height: int = 4) -> np.ndarray:
    return np.zeros((height, width, 3), dtype=np.uint8)


@pytest.fixture
def capture(monkeypatch):
    """Install a FakeCapture factory in place of cv2.VideoCapture."""
    created: list[FakeCapture] = []
    config: dict = {"frames": None, "opened": True}

    def factory(_source):
        fake = FakeCapture(config["frames"], opened=config["opened"])
        created.append(fake)
        return fake

    monkeypatch.setattr(cv2, "VideoCapture", factory)
    return type("Handle", (), {"created": created, "config": config})()


class TestResize:
    def test_scales_down_preserving_aspect_ratio(self):
        result = _resize_to_width(frame(width=100, height=50), 50)
        assert result.shape[1] == 50
        assert result.shape[0] == 25

    def test_never_upscales(self):
        original = frame(width=20, height=10)
        assert _resize_to_width(original, 100) is original

    def test_leaves_an_exact_match_alone(self):
        original = frame(width=50, height=25)
        assert _resize_to_width(original, 50) is original


class TestFileVideoSource:
    def test_reports_offline_for_a_missing_file(self, tmp_path):
        source = FileVideoSource(tmp_path / "nope.mp4")
        assert source.open() is False
        assert source.online is False

    def test_read_on_a_missing_file_returns_none_rather_than_raising(self, tmp_path):
        source = FileVideoSource(tmp_path / "nope.mp4")
        assert source.read() is None

    def test_reports_offline_when_the_file_will_not_decode(self, tmp_path, capture):
        capture.config["opened"] = False
        path = tmp_path / "broken.mp4"
        path.write_bytes(b"not a video")

        source = FileVideoSource(path)
        assert source.open() is False
        assert source.online is False

    def test_opens_and_reads_a_frame(self, tmp_path, capture):
        capture.config["frames"] = [frame(width=100, height=50)]
        path = tmp_path / "clip.mp4"
        path.touch()

        source = FileVideoSource(path, target_fps=0, frame_width=50)
        got = source.read()

        assert got is not None
        assert got.shape[1] == 50
        assert source.online is True

    def test_opens_lazily_on_first_read(self, tmp_path, capture):
        capture.config["frames"] = [frame()]
        path = tmp_path / "clip.mp4"
        path.touch()

        source = FileVideoSource(path, target_fps=0)
        assert capture.created == []
        source.read()
        assert len(capture.created) == 1

    def test_paces_playback_to_target_fps(self, tmp_path, capture, monkeypatch):
        """A 30 fps clip must not race through the pipeline."""
        capture.config["frames"] = [frame(), frame()]
        path = tmp_path / "clip.mp4"
        path.touch()

        slept: list[float] = []
        monkeypatch.setattr("backend.video.source.time.sleep", slept.append)
        clock = iter([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        monkeypatch.setattr("backend.video.source.time.monotonic", lambda: next(clock, 0.0))

        source = FileVideoSource(path, target_fps=25.0)
        source.read()
        source.read()

        assert slept, "expected the reader to pace itself"
        assert slept[-1] == pytest.approx(0.04, abs=1e-6)

    def test_does_not_pace_when_target_fps_is_zero(self, tmp_path, capture, monkeypatch):
        capture.config["frames"] = [frame()]
        path = tmp_path / "clip.mp4"
        path.touch()

        slept: list[float] = []
        monkeypatch.setattr("backend.video.source.time.sleep", slept.append)

        FileVideoSource(path, target_fps=0).read()
        assert slept == []

    # The loop is why the demo can run back-to-back, and the discontinuity
    # flag is why looping does not flood the screen with false targets.
    def test_rewinds_at_the_end_when_looping(self, tmp_path, capture):
        capture.config["frames"] = [frame()]
        path = tmp_path / "clip.mp4"
        path.touch()

        source = FileVideoSource(path, target_fps=0, loop=True)
        source.read()
        assert source.read() is not None
        assert capture.created[0].position_resets == 1

    def test_a_rewind_is_reported_as_a_discontinuity_exactly_once(self, tmp_path, capture):
        capture.config["frames"] = [frame()]
        path = tmp_path / "clip.mp4"
        path.touch()

        source = FileVideoSource(path, target_fps=0, loop=True)
        source.read()
        assert source.consume_discontinuity() is False

        source.read()
        assert source.consume_discontinuity() is True
        assert source.consume_discontinuity() is False

    def test_goes_offline_at_the_end_when_not_looping(self, tmp_path, capture):
        capture.config["frames"] = [frame()]
        path = tmp_path / "clip.mp4"
        path.touch()

        source = FileVideoSource(path, target_fps=0, loop=False)
        source.read()

        assert source.read() is None
        assert source.online is False

    def test_goes_offline_if_a_rewind_also_fails(self, tmp_path, capture, monkeypatch):
        capture.config["frames"] = []
        path = tmp_path / "clip.mp4"
        path.touch()

        source = FileVideoSource(path, target_fps=0, loop=True)
        # Make the rewind a no-op, so the clip stays unreadable.
        monkeypatch.setattr(FakeCapture, "set", lambda self, prop, value: True)

        assert source.read() is None
        assert source.online is False

    def test_release_is_idempotent(self, tmp_path, capture):
        capture.config["frames"] = [frame()]
        path = tmp_path / "clip.mp4"
        path.touch()

        source = FileVideoSource(path, target_fps=0)
        source.read()
        source.release()
        assert capture.created[0].released is True
        assert source.online is False

        source.release()  # must not raise

    def test_describes_itself_by_filename(self, tmp_path):
        assert FileVideoSource(tmp_path / "approach.mp4").describe == "file:approach.mp4"


class TestCameraVideoSource:
    def test_opens_and_reads(self, capture):
        capture.config["frames"] = [frame(width=100, height=50)]
        source = CameraVideoSource(0, frame_width=50)

        got = source.read()
        assert got is not None
        assert got.shape[1] == 50
        assert source.online is True

    def test_reports_offline_when_the_camera_will_not_open(self, capture):
        capture.config["opened"] = False
        source = CameraVideoSource(3)

        assert source.open() is False
        assert source.online is False
        assert capture.created[0].released is True

    # A missing camera must not spin the pipeline loop at full speed.
    def test_rate_limits_reconnection_attempts(self, capture, monkeypatch):
        capture.config["opened"] = False
        now = [100.0]
        monkeypatch.setattr("backend.video.source.time.monotonic", lambda: now[0])

        source = CameraVideoSource(0)
        assert source.read() is None
        attempts_after_first = len(capture.created)

        # Immediately after a failure, no new capture is constructed.
        assert source.read() is None
        assert len(capture.created) == attempts_after_first

        # Once the interval has elapsed, it tries again.
        now[0] += CameraVideoSource.RECONNECT_INTERVAL + 0.1
        assert source.read() is None
        assert len(capture.created) == attempts_after_first + 1

    def test_a_failed_read_releases_and_schedules_a_reconnect(self, capture, monkeypatch):
        capture.config["frames"] = [frame()]
        now = [100.0]
        monkeypatch.setattr("backend.video.source.time.monotonic", lambda: now[0])

        source = CameraVideoSource(0)
        source.read()
        assert source.online is True

        assert source.read() is None
        assert source.online is False
        assert capture.created[0].released is True

    def test_frames_after_a_reconnect_are_a_discontinuity(self, capture, monkeypatch):
        capture.config["frames"] = [frame()]
        monkeypatch.setattr("backend.video.source.time.monotonic", lambda: 100.0)

        source = CameraVideoSource(0)
        source.read()
        assert source.consume_discontinuity() is False

        source.read()  # fails
        assert source.consume_discontinuity() is True
        assert source.consume_discontinuity() is False

    def test_release_is_idempotent(self, capture):
        capture.config["frames"] = [frame()]
        source = CameraVideoSource(0)
        source.read()

        source.release()
        assert source.online is False
        source.release()  # must not raise

    def test_describes_itself_by_index(self):
        assert CameraVideoSource(2).describe == "camera:2"


class TestBuildVideoSource:
    def test_builds_a_camera_source(self, settings_factory):
        source = build_video_source(settings_factory(video_source="camera", camera_index=1))
        assert isinstance(source, CameraVideoSource)
        assert source.index == 1

    def test_builds_a_file_source_by_default(self, settings_factory):
        source = build_video_source(settings_factory(video_source="file"))
        assert isinstance(source, FileVideoSource)
        assert source.loop is True


class TestBaseClassDefaults:
    def test_a_source_is_continuous_unless_it_says_otherwise(self):
        class Always(FileVideoSource):
            pass

        # The base implementation returns False; VideoSource.consume_discontinuity
        # is the default for sources that never cut.
        from backend.video.source import VideoSource

        assert VideoSource.consume_discontinuity(object()) is False  # type: ignore[arg-type]

    def test_describe_defaults_to_the_class_name(self):
        from backend.video.source import VideoSource

        assert VideoSource.describe.fget(object()) == "object"  # type: ignore[union-attr]


@pytest.fixture
def settings_factory():
    """Minimal settings stand-in for build_video_source."""

    def make(**overrides):
        defaults = dict(
            video_source="file",
            camera_index=0,
            frame_width=960,
            video_path=Path("clip.mp4"),
            target_fps=25.0,
            loop_video=True,
        )
        defaults.update(overrides)
        return type("Settings", (), defaults)()

    return make
