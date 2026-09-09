"""Mission state machine.

The authoritative source of mission state. The UI renders what this produces
and never derives state independently — that guarantee is what keeps the
operator screen and the backend from disagreeing.

Nominal path:

    SEARCHING
      -> DETECTED               a track exists, not yet confirmed by tracker
      -> TRACKING               tracker confirmed the track (min_hits met)
      -> THREAT_CONFIRMED       all demo rules satisfied
      -> FOLLOWING              maintaining the confirmed track
      -> AWAITING_AUTHORIZATION operator gate; AUTHORIZE becomes active
      -> AUTHORIZED             operator pressed AUTHORIZE
      -> ACTUATED               safe simulated actuation completed
      -> SEARCHING              auto-reset, ready to run again

Off-nominal:

    any tracking state -> TARGET_LOST -> SEARCHING

Design rules this module enforces:

  * Transitions are pure functions of (current state, tracks, elapsed time,
    operator commands). No randomness, no hidden inference.
  * Actuation is impossible without an explicit operator authorization. The
    machine will never move to AUTHORIZED on its own.
  * Losing the target after AUTHORIZED does NOT cancel the engagement — the
    operator's decision has already been taken and the actuation sequence
    completes. Cancelling mid-sequence would be a surprising behaviour to
    demonstrate.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from backend.mission.rules import RuleEngine
from backend.mission.timeline import active_phase, build_timeline
from backend.schemas import EventCode, EventKind, MissionState, MissionStatus
from backend.vision.tracker import Track

log = logging.getLogger(__name__)

# States in which a live track is being maintained. Losing the target in any
# of these drops the mission to TARGET_LOST.
_TRACKING_STATES = frozenset(
    {
        MissionState.DETECTED,
        MissionState.TRACKING,
        MissionState.THREAT_CONFIRMED,
        MissionState.FOLLOWING,
        MissionState.AWAITING_AUTHORIZATION,
    }
)

class EventEmitter(Protocol):
    """How the machine reports to the operator.

    Structured: `code` is what a mission report filters on, `message` is what
    a person reads. Both are always supplied — a transition that logs only
    prose is invisible to field-test analysis.
    """

    def __call__(
        self,
        kind: EventKind,
        message: str,
        *,
        code: EventCode = ...,
        target_id: str | None = ...,
    ) -> object: ...


def _null_emitter(
    kind: EventKind,
    message: str,
    *,
    code: EventCode = EventCode.SYSTEM_INFO,
    target_id: str | None = None,
) -> None:
    """Used when no emitter is injected, e.g. in unit tests."""


# Which structured code each state transition carries. Derived from the state
# being entered, so a new state cannot silently log as SYSTEM_INFO.
_STATE_EVENT_CODE: dict[MissionState, EventCode] = {
    MissionState.SEARCHING: EventCode.STATE_CHANGE,
    MissionState.DETECTED: EventCode.OBJECT_DETECTED,
    MissionState.TRACKING: EventCode.TRACK_CONFIRMED,
    MissionState.THREAT_CONFIRMED: EventCode.THREAT_CRITERIA_MET,
    MissionState.FOLLOWING: EventCode.FOLLOWING_TARGET,
    MissionState.AWAITING_AUTHORIZATION: EventCode.ENGAGEMENT_READY,
    MissionState.AUTHORIZED: EventCode.OPERATOR_AUTHORIZED,
    MissionState.ACTUATED: EventCode.INTERCEPTOR_RELEASE_SIMULATED,
    MissionState.TARGET_LOST: EventCode.TRACK_LOST,
    MissionState.ERROR: EventCode.ERROR,
}


@dataclass
class MissionConfig:
    confirmation_time: float = 2.0
    follow_time: float = 1.5
    target_lost_grace: float = 1.0
    target_lost_hold: float = 2.5
    actuated_hold: float = 6.0
    actuator_duration: float = 1.6


class MissionStateMachine:
    """Deterministic V0 mission state machine."""

    def __init__(
        self,
        rule_engine: RuleEngine,
        config: MissionConfig,
        *,
        emit: EventEmitter | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.rules = rule_engine
        self.config = config
        self._emit: EventEmitter = emit or _null_emitter
        self._clock = clock

        # The machine's notion of "now". Refreshed at the top of update() from
        # the caller-supplied timestamp, and used by every timing decision.
        # Nothing below may call self._clock() directly: mixing an injected
        # timestamp with an independent wall clock silently corrupts every
        # dwell timer, and makes the machine untestable.
        self._now = self._clock()

        self._state = MissionState.SEARCHING
        self._state_entered_at = self._now
        self._target_id: str | None = None
        self._detail = "No target. Sensor active, detector running."
        self._progress = 0.0

        # Operator intent, consumed on the next update().
        self._authorization_requested = False
        # Set once actuation has been dispatched, so it fires exactly once.
        self._actuation_dispatched = False
        # One-shot latch raised when the mission reaches ACTUATED, so the
        # caller can retire the engaged track exactly once.
        self._engagement_complete = False
        self._authorized_at: float | None = None
        # Timestamp the primary target was last seen, for the lost-grace timer.
        self._last_seen_at: float | None = None

        # The engagement-readiness gate, refreshed each frame by the caller.
        # Defaults open so the machine remains usable — and unit-testable —
        # without a readiness evaluator attached.
        self._engagement_ready = True
        self._readiness_detail = ""

    # ------------------------------------------------------------------
    # Public state
    # ------------------------------------------------------------------

    @property
    def state(self) -> MissionState:
        return self._state

    @property
    def target_id(self) -> str | None:
        return self._target_id

    @property
    def authorized_at(self) -> float | None:
        """When the operator's authorization was accepted.

        Recorded separately from the launch command's own timestamp: the two
        are a frame apart, and a report that conflates them cannot answer how
        long the system took to act on the decision.
        """
        return self._authorized_at

    @property
    def can_authorize(self) -> bool:
        """Whether the AUTHORIZE control should be active.

        The single gate that makes authorization impossible before the
        mission has reached the authorization step.
        """
        return self._state is MissionState.AWAITING_AUTHORIZATION

    def status(self) -> MissionStatus:
        progress = round(self._progress, 4)
        return MissionStatus(
            state=self._state,
            target_id=self._target_id,
            authorization_required=self._state is MissionState.AWAITING_AUTHORIZATION,
            can_authorize=self.can_authorize,
            detail=self._detail,
            progress=progress,
            state_since=round(self._now - self._state_entered_at, 3),
            # Built here rather than in the UI, so the timeline is a view of
            # this machine's state and cannot drift away from it.
            phase=active_phase(self._state),
            phases=build_timeline(self._state, progress),
        )

    # ------------------------------------------------------------------
    # Operator commands
    # ------------------------------------------------------------------

    def request_authorization(self) -> tuple[bool, str]:
        """Record an operator authorization.

        Returns (accepted, detail). Rejected unless the mission is in
        AWAITING_AUTHORIZATION — this is the hard interlock that makes it
        impossible to actuate without having reached the authorization step.
        """
        if not self.can_authorize:
            detail = (
                f"Authorization rejected: mission is {self._state.value}, "
                "not awaiting authorization."
            )
            self._emit(
                EventKind.WARNING,
                detail,
                code=EventCode.AUTHORIZATION_REJECTED,
                target_id=self._target_id,
            )
            log.warning(detail)
            return False, detail

        self._authorization_requested = True
        detail = f"Operator authorization received for {self._target_id}."
        self._emit(
            EventKind.AUTHORIZATION,
            detail,
            code=EventCode.AUTHORIZATION_REQUESTED,
            target_id=self._target_id,
        )
        log.info(detail)
        return True, detail

    def reset(self, *, reason: str = "Operator reset") -> None:
        """Return the mission to SEARCHING and clear all engagement state."""
        self._authorization_requested = False
        self._actuation_dispatched = False
        self._engagement_complete = False
        self._authorized_at = None
        self._last_seen_at = None
        self._target_id = None
        self._progress = 0.0
        # Logged as a state change, not as MISSION_RESET. The machine resets
        # itself for several reasons — an operator command, a video
        # discontinuity, the auto-reset after actuation — and only the caller
        # knows which. The caller emits the single MISSION_RESET; emitting one
        # here too would double every reset in the log and in the report.
        self._transition(
            MissionState.SEARCHING,
            "No target. Sensor active, detector running.",
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------

    def update(
        self,
        primary: Track | None,
        primary_designation: str | None,
        *,
        now: float | None = None,
        engagement_ready: bool = True,
        readiness_detail: str = "",
    ) -> MissionStatus:
        """Advance the machine one frame.

        `primary` is the target the mission acts on, or None if there is no
        usable track this frame.

        `engagement_ready` is the verdict from `EngagementReadiness` for every
        precondition except the operator's authorization itself. It gates the
        move out of FOLLOWING; it can never cause a transition, only withhold
        one.
        """
        now = self._clock() if now is None else now
        self._now = now
        self._engagement_ready = engagement_ready
        self._readiness_detail = readiness_detail

        # An accepted authorization is honoured before anything else, and
        # regardless of whether the target is visible on this frame.
        #
        # The gate was open at the moment the operator acted, so the decision
        # stands. Without this ordering, a target leaving the frame in the
        # gap between the button press and the next frame sends the mission
        # to TARGET_LOST and silently discards the authorization — the
        # operator sees "authorization received" and then nothing happens.
        if self._state is MissionState.AWAITING_AUTHORIZATION and self._authorization_requested:
            self._authorization_requested = False
            self._authorized_at = now
            self._transition(
                MissionState.AUTHORIZED,
                f"Engagement authorized for {self._target_id}.",
                kind=EventKind.AUTHORIZATION,
            )
            return self.status()

        # The post-authorization sequence runs to completion independently of
        # the track, so handle it before any target-loss logic.
        if self._state in (MissionState.AUTHORIZED, MissionState.ACTUATED):
            self._update_engagement(now)
            return self.status()

        if primary is not None:
            self._last_seen_at = now
            self._target_id = primary_designation
            self._update_with_target(primary, now)
        else:
            self._update_without_target(now)

        return self.status()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _update_with_target(self, track: Track, now: float) -> None:
        outcome = self.rules.evaluate(track, now)

        # Recovering a target while in TARGET_LOST re-enters the track chain
        # rather than forcing a full restart from SEARCHING.
        if self._state in (MissionState.SEARCHING, MissionState.TARGET_LOST):
            self._progress = 0.0
            self._transition(
                MissionState.DETECTED,
                f"{self._target_id} detected at {track.confidence:.0%} confidence.",
                kind=EventKind.DETECTION,
            )
            return

        if self._state is MissionState.DETECTED:
            if track.confirmed:
                self._progress = outcome.progress
                self._transition(
                    MissionState.TRACKING,
                    f"Track acquired on {self._target_id}. Evaluating demo criteria.",
                    kind=EventKind.TRACK,
                )
            return

        if self._state is MissionState.TRACKING:
            self._progress = outcome.progress
            self._detail = f"Evaluating: {outcome.summary}"
            if outcome.confirmed:
                self._progress = 1.0
                self._transition(
                    MissionState.THREAT_CONFIRMED,
                    f"{self._target_id} satisfies demo confirmation criteria.",
                )
            return

        if self._state is MissionState.THREAT_CONFIRMED:
            # A brief dwell in THREAT_CONFIRMED so the operator actually sees
            # the state, then on to FOLLOWING.
            self._progress = 1.0
            if now - self._state_entered_at >= 0.8:
                self._transition(
                    MissionState.FOLLOWING,
                    f"Target locked. Following {self._target_id}.",
                )
            return

        if self._state is MissionState.FOLLOWING:
            held = now - self._state_entered_at
            self._progress = (
                min(1.0, held / self.config.follow_time) if self.config.follow_time > 0 else 1.0
            )
            self._detail = f"Target locked. Following {self._target_id}."
            if held < self.config.follow_time:
                return

            # The follow dwell is satisfied; the engagement preconditions are
            # the second gate. Holding in FOLLOWING when the canister is not
            # ready is the correct behaviour: the operator is never offered a
            # control the system could not honour.
            if not self._engagement_ready:
                self._progress = 1.0
                self._detail = self._readiness_detail or "Engagement preconditions not met."
                return

            self._progress = 1.0
            self._transition(
                MissionState.AWAITING_AUTHORIZATION,
                "Operator authorization required to proceed.",
            )
            return

        if self._state is MissionState.AWAITING_AUTHORIZATION:
            # The transition out of this state is handled at the top of
            # update(), so that it cannot be pre-empted by target loss.
            self._progress = 1.0
            self._detail = "Operator authorization required to proceed."
            return

    def _update_without_target(self, now: float) -> None:
        if self._state is MissionState.SEARCHING:
            self._detail = "No target. Sensor active, detector running."
            self._progress = 0.0
            return

        if self._state is MissionState.TARGET_LOST:
            if now - self._state_entered_at >= self.config.target_lost_hold:
                self._target_id = None
                self._transition(
                    MissionState.SEARCHING,
                    "No target. Sensor active, detector running.",
                )
            return

        if self._state in _TRACKING_STATES:
            # Grace period: a one-frame detection dropout must not flip the
            # whole mission out of a tracking state.
            since_seen = now - (self._last_seen_at or now)
            if since_seen >= self.config.target_lost_grace:
                self._progress = 0.0
                self._transition(
                    MissionState.TARGET_LOST,
                    f"Track lost on {self._target_id}. Reacquiring.",
                    kind=EventKind.WARNING,
                )

    def _update_engagement(self, now: float) -> None:
        """Drive AUTHORIZED -> ACTUATED -> auto-reset."""
        if self._state is MissionState.AUTHORIZED:
            self._progress = 1.0
            elapsed = now - (self._authorized_at or now)
            self._detail = f"Engagement authorized for {self._target_id}. Actuating."
            if elapsed >= self.config.actuator_duration:
                self._engagement_complete = True
                self._transition(
                    MissionState.ACTUATED,
                    "Interceptor launch simulated. Safe actuation complete.",
                    kind=EventKind.ACTUATION,
                )
            return

        if self._state is MissionState.ACTUATED:
            self._progress = 1.0
            self._detail = "Interceptor launch simulated. Safe actuation complete."
            if (
                self.config.actuated_hold > 0
                and now - self._state_entered_at >= self.config.actuated_hold
            ):
                self.reset(reason="Auto-reset after actuation")

    def should_dispatch_actuation(self) -> bool:
        """True exactly once, on the frame the mission becomes AUTHORIZED.

        The pipeline calls this to fire the actuator. Keeping the one-shot
        latch here means the actuator can never be triggered twice for one
        authorization, regardless of how the pipeline loops.
        """
        if self._state is MissionState.AUTHORIZED and not self._actuation_dispatched:
            self._actuation_dispatched = True
            return True
        return False

    def consume_engagement_complete(self) -> bool:
        """True exactly once, on the frame the mission reaches ACTUATED.

        The pipeline uses this to retire the engaged track so the demo does
        not immediately re-arm on the target it just engaged.
        """
        if self._engagement_complete:
            self._engagement_complete = False
            return True
        return False

    def _transition(
        self,
        new_state: MissionState,
        detail: str,
        *,
        kind: EventKind = EventKind.STATE,
        code: EventCode | None = None,
        reason: str | None = None,
    ) -> None:
        if new_state is self._state:
            self._detail = detail
            return
        previous = self._state
        self._state = new_state
        self._state_entered_at = self._now
        self._detail = detail
        # The `A -> B: detail` shape is a documented part of the event log and
        # is parsed by the end-to-end test; the structured `code` is the
        # machine-readable half added alongside it, not a replacement.
        message = f"{previous.value} -> {new_state.value}: {detail}"
        if reason:
            message = f"{message} ({reason})"
        self._emit(
            kind,
            message,
            code=code or _STATE_EVENT_CODE.get(new_state, EventCode.STATE_CHANGE),
            target_id=self._target_id,
        )
        log.info(message)
