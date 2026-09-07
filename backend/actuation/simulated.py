"""Simulated actuator — the V0 default.

Performs no physical action whatsoever. It logs a timestamped event and
returns a result that the UI renders as a launch cue. This is the entirety
of "ACTUATE" in V0.

A future safe test device (LED, servo-driven lid, GPIO test pin) would be a
sibling class implementing the same `ActuatorInterface`, selected by the
`SKUNK_ACTUATOR` setting. Nothing else in the application would change.
"""

from __future__ import annotations

import logging

from backend.actuation.base import ActuatorInterface
from backend.schemas import ActuationResult

log = logging.getLogger(__name__)


class SimulatedActuator(ActuatorInterface):
    """Logs the engagement event and reports success. Safe by construction."""

    def __init__(self) -> None:
        self._fire_count = 0

    @property
    def name(self) -> str:
        return "simulated"

    @property
    def fire_count(self) -> int:
        """How many times this actuator has fired since the process started."""
        return self._fire_count

    def fire(self, target_id: str | None) -> ActuationResult:
        self._fire_count += 1
        detail = (
            f"SIMULATED ACTUATION #{self._fire_count} for {target_id or 'unknown target'}: "
            "canister lid event emitted. No physical action taken."
        )
        log.info(detail)
        return self._result(ok=True, detail=detail, target_id=target_id)

    def reset(self) -> None:
        # Nothing to release; the counter is intentionally cumulative so the
        # logs show how many demo runs a session performed.
        pass


def build_actuator(settings) -> ActuatorInterface:
    """Construct the configured actuator.

    Only the simulated actuator exists in V0. The indirection is here so a
    safe test device can be added without touching mission logic.
    """
    return SimulatedActuator()
