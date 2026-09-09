"""Engagement readiness — the gate immediately upstream of the launcher.

This is the layer that answers one question, and only that question:

    "Is this canister, right now, in a condition where an engagement could
     legitimately be authorized?"

It is deliberately separate from the mission state machine. The state machine
knows how a mission *progresses*; readiness knows whether the machine and the
hardware around it are *fit* to proceed. Keeping them apart is what lets a
future canister add a real precondition — launcher continuity, interceptor
present, safety interlock closed — by appending a condition here, without
touching mission logic, perception or the UI.

Design rules:

  * Every condition is a pure, named boolean with a human-readable reason.
    "NOT READY" is never reported without saying which condition failed.
  * The derived state is a strict progression:
        NOT_READY → READY_FOR_AUTHORIZATION → AUTHORIZED → LAUNCH_COMMAND_ISSUED
  * Nothing here authorizes anything. It reports a condition; the operator
    authorizes, and the mission state machine owns that interlock.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.schemas import (
    EngagementReadiness,
    MissionState,
    ReadinessCondition,
    ReadinessState,
    SubsystemState,
)

# Conditions, in the order they are evaluated and displayed. The order is the
# order an operator would reason about them: is there a target, is the track
# good enough, is the machine healthy, is the launcher there.
TARGET_VALID = "target_valid"
TRACK_CONFIRMED = "track_confirmed"
TRACK_STABLE = "track_stable"
CANISTER_OPERATIONAL = "canister_operational"
LAUNCHER_INTERFACE_READY = "launcher_interface_ready"
AUTHORIZATION_VALID = "authorization_valid"

CONDITION_ORDER = (
    TARGET_VALID,
    TRACK_CONFIRMED,
    TRACK_STABLE,
    CANISTER_OPERATIONAL,
    LAUNCHER_INTERFACE_READY,
    AUTHORIZATION_VALID,
)

# Mission states in which the target has satisfied every demo criterion. Below
# this the engagement cannot be ready however healthy the hardware is.
_CRITERIA_MET_STATES = frozenset(
    {
        MissionState.THREAT_CONFIRMED,
        MissionState.FOLLOWING,
        MissionState.AWAITING_AUTHORIZATION,
        MissionState.AUTHORIZED,
        MissionState.ACTUATED,
    }
)

_ENGAGED_STATES = frozenset({MissionState.AUTHORIZED, MissionState.ACTUATED})


@dataclass(frozen=True)
class ReadinessInputs:
    """Everything the evaluator is allowed to look at.

    Passed as one frozen record rather than eight arguments so that adding a
    real hardware precondition later is a field here and a condition below —
    and every caller keeps compiling.
    """

    mission_state: MissionState
    target_id: str | None
    # Track quality, from the tracker and the projection.
    track_confirmed: bool = False
    track_stability: float = 0.0  # 0..1; projection confidence
    track_duration: float = 0.0
    # Canister health, rolled up from the subsystem model.
    canister_state: SubsystemState = SubsystemState.INITIALISING
    canister_detail: str = ""
    # Launcher interface.
    launcher_ready: bool = False
    launcher_detail: str = ""
    # Whether a launch command has already gone out for this engagement.
    launch_command_issued: bool = False


class EngagementReadinessEvaluator:
    """Evaluates the engagement preconditions once per frame.

    Stateless with respect to the mission: everything it needs arrives in
    `ReadinessInputs`. That makes the whole gate reproducible from a recorded
    mission run, which is the property field-test analysis depends on.
    """

    def __init__(self, *, min_track_stability: float = 0.25) -> None:
        # Below this projection confidence the track is moving too erratically
        # — or has too little history — to call stable. It is a display-derived
        # quality signal, not a targeting quantity.
        self.min_track_stability = min_track_stability

    def evaluate(self, inputs: ReadinessInputs) -> EngagementReadiness:
        conditions = [
            self._target_valid(inputs),
            self._track_confirmed(inputs),
            self._track_stable(inputs),
            self._canister_operational(inputs),
            self._launcher_ready(inputs),
            self._authorization_valid(inputs),
        ]
        blocking = [c.name for c in conditions if not c.met]
        state = self._derive_state(inputs, conditions)

        return EngagementReadiness(
            state=state,
            conditions=conditions,
            blocking=blocking,
            detail=self._detail(state, conditions, blocking),
        )

    # ------------------------------------------------------------------
    # Conditions
    # ------------------------------------------------------------------

    def _target_valid(self, i: ReadinessInputs) -> ReadinessCondition:
        """A designated target exists and has satisfied the demo criteria.

        After authorization the target may legitimately have left the frame —
        the engagement was committed while it was valid, and re-testing here
        would retroactively invalidate a decision already taken.
        """
        if i.mission_state in _ENGAGED_STATES:
            return ReadinessCondition(
                name=TARGET_VALID,
                met=True,
                detail=f"{i.target_id or 'target'} committed at authorization",
            )
        if i.target_id is None:
            return ReadinessCondition(
                name=TARGET_VALID, met=False, detail="no designated target"
            )
        if i.mission_state not in _CRITERIA_MET_STATES:
            return ReadinessCondition(
                name=TARGET_VALID,
                met=False,
                detail=f"{i.target_id} has not met threat criteria",
            )
        return ReadinessCondition(
            name=TARGET_VALID, met=True, detail=f"{i.target_id} meets threat criteria"
        )

    def _track_confirmed(self, i: ReadinessInputs) -> ReadinessCondition:
        if i.mission_state in _ENGAGED_STATES:
            return ReadinessCondition(
                name=TRACK_CONFIRMED, met=True, detail="confirmed at authorization"
            )
        return ReadinessCondition(
            name=TRACK_CONFIRMED,
            met=i.track_confirmed,
            detail=(
                f"track held {i.track_duration:.1f}s"
                if i.track_confirmed
                else "track not confirmed by the tracker"
            ),
        )

    def _track_stable(self, i: ReadinessInputs) -> ReadinessCondition:
        """The track's motion is consistent enough to be worth following.

        Sensor-frame projection confidence only. This says the track is not
        jittering; it says nothing about where the object will physically be.
        """
        if i.mission_state in _ENGAGED_STATES:
            return ReadinessCondition(
                name=TRACK_STABLE, met=True, detail="stable at authorization"
            )
        met = i.track_stability >= self.min_track_stability
        return ReadinessCondition(
            name=TRACK_STABLE,
            met=met,
            detail=(
                f"projection confidence {i.track_stability:.0%} "
                f"(>= {self.min_track_stability:.0%})"
            ),
        )

    def _canister_operational(self, i: ReadinessInputs) -> ReadinessCondition:
        met = i.canister_state in (SubsystemState.OPERATIONAL, SubsystemState.DEGRADED)
        return ReadinessCondition(
            name=CANISTER_OPERATIONAL,
            met=met,
            detail=i.canister_detail or f"canister {i.canister_state.value}",
        )

    def _launcher_ready(self, i: ReadinessInputs) -> ReadinessCondition:
        fallback = "interface ready" if i.launcher_ready else "no launcher interface"
        return ReadinessCondition(
            name=LAUNCHER_INTERFACE_READY,
            met=i.launcher_ready,
            detail=i.launcher_detail or fallback,
        )

    def _authorization_valid(self, i: ReadinessInputs) -> ReadinessCondition:
        """Whether a valid operator authorization has been recorded.

        Unmet before the operator acts — which is correct and expected, not a
        fault. Its purpose is to make the authorization an explicit, logged
        precondition of the launch command rather than an implicit one.
        """
        authorized = i.mission_state in _ENGAGED_STATES
        return ReadinessCondition(
            name=AUTHORIZATION_VALID,
            met=authorized,
            detail=(
                "operator authorization recorded"
                if authorized
                else "awaiting operator authorization"
            ),
        )

    # ------------------------------------------------------------------
    # Derived state
    # ------------------------------------------------------------------

    def _derive_state(
        self, i: ReadinessInputs, conditions: list[ReadinessCondition]
    ) -> ReadinessState:
        met = {c.name for c in conditions if c.met}

        if i.launch_command_issued:
            return ReadinessState.LAUNCH_COMMAND_ISSUED
        if AUTHORIZATION_VALID in met:
            return ReadinessState.AUTHORIZED

        # Everything except the authorization itself must hold before the
        # operator is offered the control.
        preconditions = set(CONDITION_ORDER) - {AUTHORIZATION_VALID}
        if preconditions.issubset(met):
            return ReadinessState.READY_FOR_AUTHORIZATION
        return ReadinessState.NOT_READY

    @staticmethod
    def _detail(
        state: ReadinessState,
        conditions: list[ReadinessCondition],
        blocking: list[str],
    ) -> str:
        if state is ReadinessState.LAUNCH_COMMAND_ISSUED:
            return "Launch command issued to the launcher interface."
        if state is ReadinessState.AUTHORIZED:
            return "Engagement authorized by the operator."
        if state is ReadinessState.READY_FOR_AUTHORIZATION:
            return "All preconditions met. Awaiting operator authorization."

        # Name the first unmet precondition rather than listing all of them:
        # one clear reason is actionable, six is a wall.
        by_name = {c.name: c for c in conditions}
        for name in CONDITION_ORDER:
            if name == AUTHORIZATION_VALID:
                continue
            if name in blocking:
                return f"Not ready — {name}: {by_name[name].detail}."
        return "Not ready."


def build_readiness_evaluator(settings) -> EngagementReadinessEvaluator:
    """Assemble the configured evaluator."""
    return EngagementReadinessEvaluator(
        min_track_stability=settings.readiness_min_track_stability
    )
