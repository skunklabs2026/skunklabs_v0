"""Simulated launcher interface - the V0 default.

Performs no physical action whatsoever. It receives a `LaunchCommand`,
timestamps it, transitions its own state, acknowledges receipt, and returns.
That is the entirety of "LAUNCH" in V0: a software handshake, a log entry, a
telemetry event and an animation.

The handshake is modelled properly rather than stubbed out because the
handshake is the part that has to survive contact with real hardware. A
future launcher controller is a sibling class implementing the same
`ActuatorInterface`, selected by the `SKUNK_ACTUATOR` setting; the mission
system will not be able to tell the difference except through `simulated`.
"""

from __future__ import annotations

import logging
import time

from backend.actuation.base import ActuatorInterface
from backend.schemas import (
    LaunchAcknowledgement,
    LaunchCommand,
    LauncherState,
    LauncherStatus,
)

log = logging.getLogger(__name__)

# How long the launcher holds ACKNOWLEDGED before returning to SAFE. Long
# enough that an operator sees the handshake complete on screen.
_ACKNOWLEDGED_HOLD = 4.0


class SimulatedActuator(ActuatorInterface):
    """Accepts and acknowledges launch commands. Safe by construction."""

    def __init__(self) -> None:
        self._state = LauncherState.SAFE
        self._commands_issued = 0
        self._last_command: LaunchCommand | None = None
        self._last_acknowledged_at: float | None = None

    @property
    def name(self) -> str:
        return "simulated"

    @property
    def simulated(self) -> bool:
        return True

    @property
    def ready(self) -> bool:
        # The simulated interface is always available. A real one would report
        # continuity, arming voltage and an interlock here.
        return True

    @property
    def state(self) -> LauncherState:
        return self._state

    @property
    def commands_issued(self) -> int:
        """How many commands this interface has accepted since process start."""
        return self._commands_issued

    # ------------------------------------------------------------------
    # The boundary
    # ------------------------------------------------------------------

    def execute(self, command: LaunchCommand) -> LaunchAcknowledgement:
        received_at = time.time()
        self._state = LauncherState.COMMAND_RECEIVED
        self._commands_issued += 1
        self._last_command = command

        log.info(
            "LAUNCH COMMAND %s received: target=%s mission=%s readiness=%s",
            command.command_id,
            command.target_id or "unknown",
            command.mission_state.value,
            command.readiness.value,
        )

        self._state = LauncherState.ACKNOWLEDGED
        acknowledgement = self._acknowledge(
            command,
            accepted=True,
            detail=(
                f"Launch command {command.command_id} acknowledged by the simulated "
                f"launcher for {command.target_id or 'unknown target'}. "
                "No physical action taken."
            ),
            launcher_state=self._state,
            received_at=received_at,
        )
        self._last_acknowledged_at = acknowledgement.acknowledged_at
        log.info(acknowledgement.detail)
        return acknowledgement

    def update(self, now: float) -> None:
        """Return the launcher to SAFE once the acknowledgement has been seen.

        A launcher that stayed ACKNOWLEDGED forever would misreport the
        canister as armed for the rest of the session.
        """
        if self._state is not LauncherState.ACKNOWLEDGED:
            return
        if self._last_acknowledged_at is None:
            return
        if now - self._last_acknowledged_at >= _ACKNOWLEDGED_HOLD:
            self._state = LauncherState.SAFE

    def status(self, now: float | None = None) -> LauncherStatus:
        return LauncherStatus(
            interface=self.name,
            state=self._state,
            simulated=True,
            ready=self.ready,
            commands_issued=self._commands_issued,
            last_command_id=self._last_command.command_id if self._last_command else None,
            last_command_at=self._last_command.issued_at if self._last_command else None,
            last_acknowledged_at=self._last_acknowledged_at,
            detail="Simulated launcher interface. No physical device attached.",
        )

    def reset(self) -> None:
        # Back to SAFE, but the command count is intentionally cumulative so
        # the logs show how many engagements a session performed.
        self._state = LauncherState.SAFE


def build_actuator(settings) -> ActuatorInterface:
    """Construct the configured launcher interface.

    Only the simulated interface exists in V0. The indirection is here so a
    safe test device can be added without touching mission logic.
    """
    return SimulatedActuator()
