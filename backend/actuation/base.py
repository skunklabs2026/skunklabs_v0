"""Actuator interface.

=== SAFETY SCOPE ===
V0 actuation is an abstract, benign demo event only: a UI cue, a log entry,
and a WebSocket event. This interface exists so that a *safe test device*
(an LED, a servo moving a lid, a GPIO test signal) can be attached later
without touching the mission logic.

This interface must not be used to implement projectile firing, weapon
release, targeting, guidance, or any destructive actuation. Those are
explicitly out of scope for V0 and are not part of this codebase.

Contract for implementations:
  * `fire()` is only ever called by the pipeline after the state machine has
    reached AUTHORIZED, which requires an explicit operator action.
  * `fire()` must never raise. Report failure via `ActuationResult.ok`.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from backend.schemas import ActuationResult


class ActuatorInterface(ABC):
    """A safe, abstract actuation endpoint."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Identifier reported in telemetry and logs."""

    @abstractmethod
    def fire(self, target_id: str | None) -> ActuationResult:
        """Execute the safe demo actuation for `target_id`.

        Must not raise; failures are reported in the returned result.
        """

    def reset(self) -> None:
        """Return the actuator to its idle state. Optional."""

    def _result(self, *, ok: bool, detail: str, target_id: str | None) -> ActuationResult:
        return ActuationResult(
            actuator=self.name,
            ok=ok,
            detail=detail,
            target_id=target_id,
            timestamp=time.time(),
        )
