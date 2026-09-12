"""Mission run recording - every demo is a test.

Writes one JSON report per run to `runs/mission_YYYY_MM_DD_NNN.json`. No
database: a run is a few hundred events, the consumer is a person or a short
analysis script, and a file on disk survives the process that wrote it.

>>> WHY THIS MATTERS <<<
The step from "the demo worked" to "the system behaved correctly" is the step
from watching a screen to reading a record. A report captures the questions a
field test actually asks: how long did acquisition take, did the track break,
what was the readiness state when the operator authorized, and how long did
the launcher take to acknowledge.

The recorder is fed by the pipeline and never reaches back into it. It cannot
affect mission behaviour, and a failure to write a report is logged and
swallowed - losing a report must never interrupt a run.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from backend.schemas import (
    EventCode,
    LaunchAcknowledgement,
    LaunchCommand,
    MissionEvent,
    MissionState,
    ReadinessState,
)

log = logging.getLogger(__name__)

# Events worth keeping in a report. Per-frame chatter is deliberately excluded
# - a report a person will not read is not a record.
_RECORDED_CODES = frozenset(
    {
        EventCode.SYSTEM_START,
        EventCode.SOURCE_CHANGED,
        EventCode.SENSOR_LOST,
        EventCode.SENSOR_RESTORED,
        EventCode.OBJECT_DETECTED,
        EventCode.TRACK_CREATED,
        EventCode.TRACK_CONFIRMED,
        EventCode.TRACK_LOST,
        EventCode.TRACK_REACQUIRED,
        EventCode.THREAT_CRITERIA_MET,
        EventCode.FOLLOWING_TARGET,
        EventCode.ENGAGEMENT_READY,
        EventCode.AUTHORIZATION_REQUESTED,
        EventCode.AUTHORIZATION_REJECTED,
        EventCode.OPERATOR_AUTHORIZED,
        EventCode.LAUNCH_COMMAND_ISSUED,
        EventCode.ACTUATOR_ACKNOWLEDGED,
        EventCode.ACTUATOR_REJECTED,
        EventCode.INTERCEPTOR_RELEASE_SIMULATED,
        EventCode.MISSION_RESET,
        EventCode.WARNING,
        EventCode.ERROR,
    }
)

# Hard caps on report size.
#
# A demo clip left looping for an hour re-runs the whole sequence hundreds of
# times, and an uncapped report grows without bound - the first version of
# this produced a 388 KB file from a fifteen-minute session, which is not a
# document anybody reads. The caps keep the *earliest* entries, because the
# start of a run is what a field test is analysing; the tail is the clip
# looping. Anything dropped is counted and reported.
MAX_EVENTS = 2_000
MAX_TRANSITIONS = 1_000


@dataclass
class StateTransition:
    at: float
    elapsed: float
    state: MissionState
    target_id: str | None = None


@dataclass
class MissionRun:
    """One recorded run, from source selection to launch or reset."""

    mission_id: str
    started_at: float
    source: str
    detector: str

    ended_at: float | None = None
    primary_target: str | None = None
    detections_total: int = 0
    tracks_created: int = 0
    track_loss_events: int = 0
    frames_processed: int = 0
    mean_fps: float = 0.0
    mean_inference_ms: float = 0.0

    authorized_at: float | None = None
    readiness_at_authorization: ReadinessState | None = None
    launch_command: LaunchCommand | None = None
    launch_acknowledgement: LaunchAcknowledgement | None = None

    transitions: list[StateTransition] = field(default_factory=list)
    events: list[MissionEvent] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # Counts of what was dropped once the caps below were hit, so a truncated
    # report says so rather than quietly under-reporting.
    events_dropped: int = 0
    transitions_dropped: int = 0

    @property
    def duration(self) -> float:
        return (self.ended_at or time.time()) - self.started_at

    def to_dict(self) -> dict:
        """The report as written to disk.

        Timings are given both absolute and relative to the run's start,
        because the two answer different questions: absolute correlates with a
        launcher log, relative is what you compare between runs.
        """
        return {
            "mission_id": self.mission_id,
            "schema": "skunklabs.mission_run/1",
            "started_at": self.started_at,
            "started_at_iso": _iso(self.started_at),
            "ended_at": self.ended_at,
            "duration_s": round(self.duration, 3),
            "source": self.source,
            "detector": self.detector,
            "summary": {
                "primary_target": self.primary_target,
                "detections_total": self.detections_total,
                "tracks_created": self.tracks_created,
                "track_loss_events": self.track_loss_events,
                "frames_processed": self.frames_processed,
                "mean_fps": round(self.mean_fps, 2),
                "mean_inference_ms": round(self.mean_inference_ms, 2),
                "reached_authorization": self.authorized_at is not None,
                "launch_command_issued": self.launch_command is not None,
                "launch_acknowledged": self.launch_acknowledgement is not None,
                # The number a hardware-in-the-loop test is actually looking
                # for: how long the launcher took to answer.
                "acknowledgement_latency_ms": (
                    self.launch_acknowledgement.latency_ms
                    if self.launch_acknowledgement
                    else None
                ),
                "time_to_first_detection_s": self._elapsed_to(EventCode.OBJECT_DETECTED),
                "time_to_track_confirmed_s": self._elapsed_to(EventCode.TRACK_CONFIRMED),
                "time_to_engagement_ready_s": self._elapsed_to(EventCode.ENGAGEMENT_READY),
            },
            "authorization": {
                "authorized_at": self.authorized_at,
                "authorized_at_iso": _iso(self.authorized_at),
                "readiness_state": (
                    self.readiness_at_authorization.value
                    if self.readiness_at_authorization
                    else None
                ),
            },
            "launch_command": (
                self.launch_command.model_dump(mode="json") if self.launch_command else None
            ),
            "launch_acknowledgement": (
                self.launch_acknowledgement.model_dump(mode="json")
                if self.launch_acknowledgement
                else None
            ),
            "state_transitions": [
                {
                    "at": t.at,
                    "elapsed_s": round(t.elapsed, 3),
                    "state": t.state.value,
                    "target_id": t.target_id,
                }
                for t in self.transitions
            ],
            "events": [
                {
                    "at": e.timestamp,
                    "elapsed_s": round(e.timestamp - self.started_at, 3),
                    "code": e.code.value,
                    "kind": e.kind.value,
                    "target_id": e.target_id,
                    "message": e.message,
                }
                for e in self.events
            ],
            "errors": self.errors[:100],
            "truncated": {
                "events_dropped": self.events_dropped,
                "transitions_dropped": self.transitions_dropped,
            },
        }

    def _elapsed_to(self, code: EventCode) -> float | None:
        """Seconds from run start to the first event with this code."""
        for event in self.events:
            if event.code is code:
                return round(event.timestamp - self.started_at, 3)
        return None


def _iso(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp).isoformat(timespec="seconds")


class MissionRecorder:
    """Accumulates one run at a time and writes it out.

    Thread confinement: every method is called from the pipeline worker thread
    or from an API thread already holding the telemetry lock, which is the
    same discipline the rest of the pipeline follows.
    """

    def __init__(self, runs_dir: Path, *, enabled: bool = True) -> None:
        self.runs_dir = Path(runs_dir)
        self.enabled = enabled
        self._run: MissionRun | None = None

    @property
    def run(self) -> MissionRun | None:
        return self._run

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(
        self, *, source: str, detector: str, now: float | None = None
    ) -> MissionRun | None:
        """Begin a new run, finishing any run still open."""
        if not self.enabled:
            return None
        if self._run is not None:
            self.finish(reason="superseded")

        started = now or time.time()
        self._run = MissionRun(
            mission_id=self._next_mission_id(started),
            started_at=started,
            source=source,
            detector=detector,
        )
        log.info("Mission run %s started (source=%s)", self._run.mission_id, source)
        return self._run

    def finish(self, *, reason: str = "complete", now: float | None = None) -> Path | None:
        """Close the current run and write its report."""
        run = self._run
        self._run = None
        if run is None:
            return None

        run.ended_at = now or time.time()
        try:
            return self._write(run, reason=reason)
        except Exception:  # pragma: no cover - defensive
            # A report is valuable, but never at the cost of the demo.
            log.exception("Could not write mission report for %s", run.mission_id)
            return None

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_event(self, event: MissionEvent) -> None:
        if self._run is None or event.code not in _RECORDED_CODES:
            return
        if len(self._run.events) >= MAX_EVENTS:
            # Counters below still advance: totals stay correct even when the
            # detailed log has been truncated.
            self._run.events_dropped += 1
        else:
            self._run.events.append(event)
        if event.code is EventCode.TRACK_CREATED:
            self._run.tracks_created += 1
        elif event.code is EventCode.TRACK_LOST:
            self._run.track_loss_events += 1
        elif event.code in (EventCode.WARNING, EventCode.ERROR):
            self._run.errors.append(event.message)

    def record_transition(self, state: MissionState, target_id: str | None, now: float) -> None:
        run = self._run
        if run is None:
            return
        if len(run.transitions) >= MAX_TRANSITIONS:
            run.transitions_dropped += 1
        else:
            run.transitions.append(
                StateTransition(
                    at=now, elapsed=now - run.started_at, state=state, target_id=target_id
                )
            )
        if target_id and run.primary_target is None:
            run.primary_target = target_id

    def record_authorization(self, readiness: ReadinessState, now: float) -> None:
        if self._run is None:
            return
        self._run.authorized_at = now
        self._run.readiness_at_authorization = readiness

    def record_launch(
        self, command: LaunchCommand, acknowledgement: LaunchAcknowledgement
    ) -> None:
        if self._run is None:
            return
        self._run.launch_command = command
        self._run.launch_acknowledgement = acknowledgement

    def record_frame_stats(
        self, *, frames: int, detections_total: int, fps: float, inference_ms: float
    ) -> None:
        """Keep the latest counters, so a report reflects the whole run."""
        run = self._run
        if run is None:
            return
        run.frames_processed = frames
        run.detections_total = detections_total
        run.mean_fps = fps
        run.mean_inference_ms = inference_ms

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _write(self, run: MissionRun, *, reason: str) -> Path:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        path = self.runs_dir / f"{run.mission_id}.json"
        payload = run.to_dict()
        payload["closed_because"] = reason
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log.info("Mission report written: %s", path)
        return path

    def _next_mission_id(self, started: float) -> str:
        """`mission_YYYY_MM_DD_NNN`, sequential within the day.

        Derived from what is already on disk rather than from a counter in
        memory, so restarting the backend mid-session does not overwrite the
        morning's reports.
        """
        stamp = datetime.fromtimestamp(started).strftime("%Y_%m_%d")
        prefix = f"mission_{stamp}_"
        existing = 0
        if self.runs_dir.is_dir():
            for path in self.runs_dir.glob(f"{prefix}*.json"):
                suffix = path.stem[len(prefix) :]
                if suffix.isdigit():
                    existing = max(existing, int(suffix))
        return f"{prefix}{existing + 1:03d}"
