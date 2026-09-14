"""The MJPEG preview stream.

Exercised through the route's own async generator rather than a client, so
the disconnect path — the only thing that ends the stream — is reachable.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.api.routers.stream import BOUNDARY, video_stream


class FakeRequest:
    """Reports connected for `alive` polls, then disconnected."""

    def __init__(self, alive: int = 1) -> None:
        self._remaining = alive
        self.polls = 0

    async def is_disconnected(self) -> bool:
        self.polls += 1
        if self._remaining <= 0:
            return True
        self._remaining -= 1
        return False


class FakePipeline:
    def __init__(self, jpegs: list[bytes | None], target_fps: float = 25.0) -> None:
        self._jpegs = list(jpegs)
        self.settings = type("Settings", (), {"target_fps": target_fps})()

    def jpeg(self) -> bytes | None:
        return self._jpegs.pop(0) if self._jpegs else None


def collect(request, pipeline) -> tuple[list[bytes], object]:
    """Drive the route to completion and return everything it yielded.

    Run through `asyncio.run` rather than pytest-asyncio: the suite needs no
    async plugin for two coroutines, and every dependency here is pinned and
    locked, so not adding one is worth a three-line helper.
    """

    async def run():
        response = await video_stream(request, pipeline)
        return [chunk async for chunk in response.body_iterator], response

    return asyncio.run(run())


def test_sets_the_multipart_media_type_and_boundary():
    _, response = collect(FakeRequest(alive=0), FakePipeline([]))
    assert response.media_type == f"multipart/x-mixed-replace; boundary={BOUNDARY}"


def test_forbids_caching_so_the_preview_is_never_a_stale_frame():
    _, response = collect(FakeRequest(alive=0), FakePipeline([]))
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate"


def test_emits_a_frame_part_with_the_boundary_and_length():
    jpeg = b"\xff\xd8fake-jpeg\xff\xd9"
    chunks, _ = collect(FakeRequest(alive=1), FakePipeline([jpeg]))

    assert len(chunks) == 1
    part = chunks[0]
    assert part.startswith(b"--" + BOUNDARY.encode() + b"\r\n")
    assert b"Content-Type: image/jpeg\r\n" in part
    assert f"Content-Length: {len(jpeg)}".encode() in part
    assert part.endswith(jpeg + b"\r\n")


def test_emits_one_part_per_available_frame():
    chunks, _ = collect(FakeRequest(alive=3), FakePipeline([b"a", b"b", b"c"]))
    assert len(chunks) == 3


def test_skips_polls_where_no_frame_is_ready_yet():
    """A warming-up pipeline must not emit an empty part."""
    chunks, _ = collect(FakeRequest(alive=3), FakePipeline([None, b"a", None]))
    assert chunks == [
        b"--"
        + BOUNDARY.encode()
        + b"\r\nContent-Type: image/jpeg\r\nContent-Length: 1\r\n\r\na\r\n"
    ]


def test_stops_as_soon_as_the_client_disconnects():
    request = FakeRequest(alive=0)
    chunks, _ = collect(request, FakePipeline([b"never-sent"]))
    assert chunks == []
    assert request.polls == 1


def test_paces_the_preview_at_the_configured_rate(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    collect(FakeRequest(alive=2), FakePipeline([b"a", b"b"], target_fps=25.0))
    assert slept == [pytest.approx(0.04), pytest.approx(0.04)]


def test_never_spins_faster_than_once_a_second_on_a_silly_rate(monkeypatch):
    """target_fps below 1 must not turn the preview into a busy loop."""
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    collect(FakeRequest(alive=1), FakePipeline([b"a"], target_fps=0.0))
    assert slept == [pytest.approx(1.0)]
