"""The launcher boundary.

    MissionController → LaunchCommand → ActuatorInterface → LaunchAcknowledgement

This module defines that seam. It is the single place a future validated
launcher controller attaches, and it is deliberately narrow: one command
model in, one acknowledgement model out, no mission concepts either way. The
actuator does not know what a track is, and mission logic does not know what
a launcher is made of.

>>> SAFETY SCOPE <<<
V0 actuation is an abstract, benign demo event only: a UI cue, a log entry,
a telemetry event. This interface exists so that a *safe test device* (an
LED, a servo moving a lid, a GPIO test signal) can be attached later without
touching mission logic.

This interface must not be used to implement projectile firing, weapon
release, targeting, guidance, or any destructive actuation. Those are
explicitly out of scope for V0 and are not part of this codebase.

Contract for implementations:
  * `execute()` is only ever called after the mission state machine has
    reached AUTHORIZED, which requires an explicit operator action, and after
    `EngagementReadiness` reports AUTHORIZED.
  * `execute()` must never raise. Report failure via
    `LaunchAcknowledgement.accepted`.
  * Every command must be acknowledged. A command without an acknowledgement
    is a fault, and is reported as one.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod

from backend.schemas import (
    LaunchAcknowledgement,
    LaunchCommand,
    LauncherState,
    LauncherStatus,
    MissionState,
    ReadinessState,
)


def build_launch_command(
    *,
    target_id: str | None,
    mission_state: MissionState,
    readiness: ReadinessState,
    authorized_at: float,
    issued_at: float | None = None,
) -> LaunchCommand:
    """Mint a launch command.

    The identifier is a fresh UUID per command, so a mission report can be
    correlated with a launcher log line-for-line even across restarts — the
    property that makes hardware-in-the-loop testing tractable.
    """
    return LaunchCommand(
        command_id=f"LC-{uuid.uuid4().hex[:12].upper()}",
        issued_at=issued_at if issued_at is not None else time.time(),
        target_id=target_id,
        mission_state=mission_state,
        readiness=readiness,
        authorized_at=authorized_at,
        simulated=True,
    )


class ActuatorInterface(ABC):
    """A safe, abstract launcher endpoint."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Identifier reported in telemetry and logs."""

    @property
    @abstractmethod
    def simulated(self) -> bool:
        """True while no physical device is attached.

        Abstract on purpose: a new implementation has to make a deliberate,
        reviewable statement about whether it drives real hardware.
        """

    @abstractmethod
    def execute(self, command: LaunchCommand) -> LaunchAcknowledgement:
        """Accept a launch command and acknowledge it.

        Must not raise; failures are reported in the acknowledgement.
        """

    @abstractmethod
    def status(self, now: float | None = None) -> LauncherStatus:
        """Current launcher interface state, for telemetry."""

    @property
    def ready(self) -> bool:
        """Whether the interface can accept a command right now."""
        return True

    def reset(self) -> None:
        """Return the launcher to its safe resting state. Optional."""

    def _acknowledge(
        self,
        command: LaunchCommand,
        *,
        accepted: bool,
        detail: str,
        launcher_state: LauncherState,
        received_at: float,
    ) -> LaunchAcknowledgement:
        now = time.time()
        return LaunchAcknowledgement(
            command_id=command.command_id,
            actuator=self.name,
            accepted=accepted,
            acknowledged_at=now,
            latency_ms=max(0.0, (now - received_at) * 1000.0),
            launcher_state=launcher_state,
            detail=detail,
        )
