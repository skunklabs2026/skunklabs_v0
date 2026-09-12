"""The canister subsystem model.

CANISTER 01 is the product. This module is how it reports on itself: one
`Subsystem` per thing that can be healthy or unhealthy, rolled up into a
single headline state.

>>> HONESTY RULE <<<
V0 runs on a laptop. It has no power rail, no thermistor and no radio. Those
subsystems therefore report N/A or NOT CONNECTED, and they say so on screen.
A fabricated battery percentage would make every *real* value on the panel
untrustworthy, which is a far worse trade than an empty field.

Each subsystem is produced by a small reporter function taking a `CanisterInputs`
snapshot. Attaching real hardware means replacing one reporter and setting
`measured=True` - no other module changes, and the UI already renders the
difference between a measured value and a software-derived one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from backend.schemas import (
    CanisterStatus,
    LauncherState,
    Subsystem,
    SubsystemId,
    SubsystemState,
)


@dataclass(frozen=True)
class CanisterInputs:
    """One frame's worth of everything the canister knows about itself."""

    sensor_online: bool = False
    sensor_detail: str = ""
    detector_ready: bool = False
    detector_name: str = ""
    tracker_active_tracks: int = 0
    tracker_ready: bool = True
    # Processing rate, and the rate we are aiming for - the compute health
    # signal that actually matters for a real-time pipeline.
    fps: float = 0.0
    target_fps: float = 25.0
    inference_ms: float = 0.0
    launcher_state: LauncherState = LauncherState.SAFE
    launcher_simulated: bool = True
    interceptor_active: bool = False
    interceptor_simulated: bool = True
    uptime: float = 0.0


# Below this fraction of the target frame rate, compute is reported DEGRADED.
# Chosen so a pipeline keeping up with the source reads OPERATIONAL and one
# that has fallen visibly behind reads DEGRADED, rather than flickering.
_COMPUTE_DEGRADED_RATIO = 0.6


class CanisterStatusModel:
    """Builds the canister status panel from pipeline observations."""

    def __init__(self, *, canister_id: str = "CANISTER 01", link: str = "LOCAL") -> None:
        self.canister_id = canister_id
        # "LOCAL" is literally true: the operator console is on the same
        # machine. A deployed canister would report a radio or mesh link here.
        self.link = link
        self._started_at = time.time()

    def uptime(self, now: float | None = None) -> float:
        return (now or time.time()) - self._started_at

    def build(self, inputs: CanisterInputs) -> CanisterStatus:
        subsystems = [
            self._sensor(inputs),
            self._perception(inputs),
            self._tracker(inputs),
            self._compute(inputs),
            self._link(inputs),
            self._launcher(inputs),
            self._interceptor(inputs),
            self._power(inputs),
            self._temperature(inputs),
        ]

        state, detail = self._roll_up(subsystems)
        system = Subsystem(
            id=SubsystemId.SYSTEM,
            label="System",
            state=state,
            detail=detail,
            nominal=state is SubsystemState.OPERATIONAL,
        )

        return CanisterStatus(
            canister_id=self.canister_id,
            state=state,
            detail=detail,
            uptime=inputs.uptime,
            subsystems=[system, *subsystems],
        )

    # ------------------------------------------------------------------
    # Reporters - one per subsystem
    # ------------------------------------------------------------------

    def _sensor(self, i: CanisterInputs) -> Subsystem:
        online = i.sensor_online
        return Subsystem(
            id=SubsystemId.SENSOR,
            label="Sensor",
            state=SubsystemState.ONLINE if online else SubsystemState.OFFLINE,
            detail=i.sensor_detail,
            measured=True,  # we genuinely know whether frames are arriving
            nominal=online,
        )

    def _perception(self, i: CanisterInputs) -> Subsystem:
        ready = i.detector_ready
        return Subsystem(
            id=SubsystemId.PERCEPTION,
            label="Perception",
            state=SubsystemState.ONLINE if ready else SubsystemState.INITIALISING,
            detail=(
                f"{i.detector_name} · {i.inference_ms:.0f} ms/frame"
                if ready
                else f"{i.detector_name} initialising"
            ),
            measured=True,
            nominal=ready,
        )

    def _tracker(self, i: CanisterInputs) -> Subsystem:
        return Subsystem(
            id=SubsystemId.TRACKER,
            label="Tracker",
            state=SubsystemState.ONLINE if i.tracker_ready else SubsystemState.OFFLINE,
            detail=f"{i.tracker_active_tracks} active track(s)",
            measured=True,
            nominal=i.tracker_ready,
        )

    def _compute(self, i: CanisterInputs) -> Subsystem:
        target = max(i.target_fps, 1.0)
        keeping_up = i.fps >= target * _COMPUTE_DEGRADED_RATIO
        # A pipeline that has produced no frames yet is starting, not failing.
        if i.fps <= 0.0:
            state = SubsystemState.INITIALISING
        else:
            state = SubsystemState.ONLINE if keeping_up else SubsystemState.DEGRADED
        return Subsystem(
            id=SubsystemId.COMPUTE,
            label="Compute",
            state=state,
            detail=f"{i.fps:.0f} / {target:.0f} fps",
            measured=True,
            nominal=state is not SubsystemState.DEGRADED,
        )

    def _link(self, i: CanisterInputs) -> Subsystem:
        return Subsystem(
            id=SubsystemId.LINK,
            label="Link",
            state=SubsystemState.LOCAL,
            detail="Operator console on the same host",
            measured=True,
            nominal=True,
        )

    def _launcher(self, i: CanisterInputs) -> Subsystem:
        # SAFE is the nominal resting state, and stays nominal throughout the
        # handshake - a launcher that has acknowledged a command is working
        # correctly, not faulted.
        state = SubsystemState.SAFE
        if i.launcher_state is LauncherState.FAULT:
            state = SubsystemState.FAULT
        elif i.launcher_state in (
            LauncherState.ARMED,
            LauncherState.COMMAND_RECEIVED,
            LauncherState.ACKNOWLEDGED,
        ):
            state = SubsystemState.ARMED
        return Subsystem(
            id=SubsystemId.LAUNCHER,
            label="Launcher",
            state=state,
            detail=(
                f"{i.launcher_state.value} · simulated interface"
                if i.launcher_simulated
                else i.launcher_state.value
            ),
            measured=not i.launcher_simulated,
            nominal=state is not SubsystemState.FAULT,
        )

    def _interceptor(self, i: CanisterInputs) -> Subsystem:
        return Subsystem(
            id=SubsystemId.INTERCEPTOR,
            label="Interceptor",
            state=SubsystemState.STOWED,
            detail=(
                "Simulated - release animation only" if i.interceptor_simulated else "Stowed"
            ),
            # No round is present and no bay sensor exists. Saying otherwise
            # would be the exact kind of invented telemetry this model exists
            # to prevent.
            measured=False,
            nominal=True,
        )

    def _power(self, i: CanisterInputs) -> Subsystem:
        return Subsystem(
            id=SubsystemId.POWER,
            label="Power",
            state=SubsystemState.NOT_CONNECTED,
            detail="No power monitor on this build",
            measured=False,
            nominal=True,
        )

    def _temperature(self, i: CanisterInputs) -> Subsystem:
        return Subsystem(
            id=SubsystemId.TEMPERATURE,
            label="Temperature",
            state=SubsystemState.NOT_AVAILABLE,
            detail="No thermal sensor on this build",
            measured=False,
            nominal=True,
        )

    # ------------------------------------------------------------------
    # Roll-up
    # ------------------------------------------------------------------

    @staticmethod
    def _roll_up(subsystems: list[Subsystem]) -> tuple[SubsystemState, str]:
        """Reduce the subsystems to one headline state.

        Only subsystems that are actually *reporting* can fail the roll-up -
        an absent power monitor must never make the canister read DEGRADED,
        or the headline becomes permanently pessimistic and stops meaning
        anything.
        """
        faults = [s for s in subsystems if not s.nominal]
        if not faults:
            return SubsystemState.OPERATIONAL, "All reporting subsystems nominal"

        offline = next((s for s in faults if s.state is SubsystemState.OFFLINE), None)
        if offline is not None:
            return SubsystemState.OFFLINE, f"{offline.label} offline"

        # A subsystem still coming up is not a fault - a canister that has
        # been powered on for two seconds should read INITIALISING, not
        # DEGRADED, or the headline cries wolf on every single start.
        if all(s.state is SubsystemState.INITIALISING for s in faults):
            return SubsystemState.INITIALISING, f"{faults[0].label} initialising"

        worst = next(s for s in faults if s.state is not SubsystemState.INITIALISING)
        return SubsystemState.DEGRADED, f"{worst.label} {worst.state.value.lower()}"
