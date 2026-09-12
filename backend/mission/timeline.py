"""The mission timeline - the operator's view of how far the mission has got.

    SEARCH → DETECT → TRACK → CONFIRM → FOLLOW → AUTHORIZE → LAUNCH

This is a *projection* of `MissionState`, computed here on the backend and
shipped inside `MissionStatus`. That placement is the whole point: the
frontend renders the steps it is given and never derives a progression of its
own, so the timeline cannot drift out of agreement with the state machine.

The timeline is coarser than the state machine on purpose. THREAT_CONFIRMED
and FOLLOWING are separate mission states but one continuous operator story;
TARGET_LOST is not a step forward at all, it is a fall back to SEARCH.
"""

from __future__ import annotations

from backend.schemas import MissionPhase, MissionState, PhaseProgress, PhaseStatus

# The timeline, in order. Index into this list is "how far along we are".
PHASE_ORDER: tuple[MissionPhase, ...] = (
    MissionPhase.SEARCH,
    MissionPhase.DETECT,
    MissionPhase.TRACK,
    MissionPhase.CONFIRM,
    MissionPhase.FOLLOW,
    MissionPhase.AUTHORIZE,
    MissionPhase.LAUNCH,
)

# Which phase each mission state is *working on*. States not listed here have
# no forward progress to show - see `_ACTUATED` and the fall-back cases below.
_ACTIVE_PHASE: dict[MissionState, MissionPhase] = {
    MissionState.SEARCHING: MissionPhase.SEARCH,
    MissionState.DETECTED: MissionPhase.DETECT,
    MissionState.TRACKING: MissionPhase.TRACK,
    MissionState.THREAT_CONFIRMED: MissionPhase.CONFIRM,
    MissionState.FOLLOWING: MissionPhase.FOLLOW,
    MissionState.AWAITING_AUTHORIZATION: MissionPhase.AUTHORIZE,
    MissionState.AUTHORIZED: MissionPhase.LAUNCH,
    MissionState.ACTUATED: MissionPhase.LAUNCH,
    # A lost target is a setback, not a step: the timeline rewinds to SEARCH
    # rather than freezing on the phase that was interrupted, which would
    # imply the mission is still progressing when it is not.
    MissionState.TARGET_LOST: MissionPhase.SEARCH,
    MissionState.ERROR: MissionPhase.SEARCH,
}


def active_phase(state: MissionState) -> MissionPhase:
    """The phase the mission is currently working on."""
    return _ACTIVE_PHASE.get(state, MissionPhase.SEARCH)


def build_timeline(state: MissionState, progress: float) -> list[PhaseProgress]:
    """Render the seven steps for one mission state.

    `progress` is the state machine's own 0..1 progress toward its next
    automatic transition, and is applied to the active step only.
    """
    current = active_phase(state)
    index = PHASE_ORDER.index(current)

    # ACTUATED is the one state where the final phase is finished rather than
    # in progress - the launch command has been issued and acknowledged.
    complete_through = index if state is MissionState.ACTUATED else index - 1

    steps: list[PhaseProgress] = []
    for position, phase in enumerate(PHASE_ORDER):
        if position <= complete_through:
            steps.append(PhaseProgress(phase=phase, status=PhaseStatus.COMPLETE, progress=1.0))
        elif position == index:
            steps.append(
                PhaseProgress(
                    phase=phase,
                    status=PhaseStatus.ACTIVE,
                    progress=max(0.0, min(1.0, progress)),
                )
            )
        else:
            steps.append(PhaseProgress(phase=phase, status=PhaseStatus.PENDING, progress=0.0))
    return steps
