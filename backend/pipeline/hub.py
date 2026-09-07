"""Shared state between the pipeline worker thread and the API threads.

One role: be the *only* place where the worker thread's output and the API
thread's reads meet. Everything here is guarded by a single re-entrant lock
that the hub owns and exposes, so the composite critical section in
`runtime` can be held across a whole frame's mutation without a second
lock and a lock-ordering problem.

Nothing in this module knows about video, detection or mission logic. It
stores frames, retains events, and wakes WebSocket clients.
"""

from __future__ import annotations

import threading
import time
from collections import deque

from backend.schemas import EventKind, MissionEvent, TelemetryFrame


class TelemetryHub:
    """Thread-safe holder for the latest telemetry, preview JPEG and events."""

    def __init__(self, *, event_log_size: int) -> None:
        # Re-entrant: `emit` is called from inside sections that already hold
        # the lock, and from the API thread that does not.
        self.lock = threading.RLock()

        # Signalled on every published frame so the WebSocket pushes
        # immediately rather than polling on a timer.
        self._frame_ready = threading.Condition(self.lock)

        self._telemetry: TelemetryFrame | None = None
        self._jpeg: bytes | None = None
        self._sequence = 0

        # `_events` is the retained log replayed to a client on connect;
        # `_pending` is the much shorter list attached to the next telemetry
        # frame so live clients receive each event exactly once.
        self._events: deque[MissionEvent] = deque(maxlen=event_log_size)
        self._pending: list[MissionEvent] = []

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def emit(self, kind: EventKind, message: str) -> MissionEvent:
        """Record an operator-facing event. Safe to call from any thread."""
        event = MissionEvent(timestamp=time.time(), kind=kind, message=message)
        with self.lock:
            self._events.append(event)
            self._pending.append(event)
        return event

    def drain_pending(self) -> list[MissionEvent]:
        """Return and clear events emitted since the last telemetry frame."""
        with self.lock:
            pending = self._pending
            self._pending = []
            return pending

    def event_log(self) -> list[MissionEvent]:
        with self.lock:
            return list(self._events)

    # ------------------------------------------------------------------
    # Frames
    # ------------------------------------------------------------------

    def publish(self, telemetry: TelemetryFrame, jpeg: bytes | None) -> None:
        """Store a new frame and wake every waiting client.

        `jpeg` is already encoded by the caller — deliberately, so the
        several milliseconds of JPEG encoding happen off-lock and never
        block an API read.
        """
        with self._frame_ready:
            self._telemetry = telemetry
            if jpeg is not None:
                self._jpeg = jpeg
            self._sequence += 1
            self._frame_ready.notify_all()

    def snapshot(self) -> TelemetryFrame | None:
        with self.lock:
            return self._telemetry

    def jpeg(self) -> bytes | None:
        with self.lock:
            return self._jpeg

    def wait_for_frame(
        self, last_sequence: int, timeout: float = 1.0
    ) -> tuple[int, TelemetryFrame | None]:
        """Block until a frame newer than `last_sequence` exists.

        Returns (sequence, telemetry). Falls back to the current frame on
        timeout, so a stalled pipeline still yields a heartbeat to the UI
        instead of a silent socket.
        """
        with self._frame_ready:
            if self._sequence <= last_sequence:
                self._frame_ready.wait(timeout)
            return self._sequence, self._telemetry
