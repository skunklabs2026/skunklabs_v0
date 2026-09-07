"""Simulated interceptor flight.

>>> SAFETY SCOPE <<<
This is an ANIMATION MODEL. It advances a marker along a line in normalised
image coordinates so the operator can see that an engagement was ordered and
watch it play out. It commands nothing, controls nothing, and is not a
guidance law. No physical device is driven by this module. See README,
"What V0 is not".

It exists because a launch flash alone does not tell an operator anything:
the useful information is *where* the interceptor was sent and *when* it
arrives, which is what this makes visible.

Flight profile is deliberately trivial — constant speed along a straight line
from the launch point to the aim point, with the aim point frozen at launch.
Freezing it matters: re-aiming mid-flight would be a (crude) guidance
behaviour, and V0 must not imply one. What is shown is a ballistic commit.
"""

from __future__ import annotations

import logging
import math

from backend.schemas import (
    InterceptorPhase,
    InterceptorState,
    InterceptSolution,
    Point,
)

log = logging.getLogger(__name__)

# Seconds the launch flare is held before the marker starts moving.
LAUNCH_PHASE = 0.25
# Seconds the intercept marker is held at the end of the flight.
INTERCEPT_PHASE = 1.2
# Points retained for the interceptor's own trail.
TRAIL_LENGTH = 40


class InterceptorSimulation:
    """Advances a simulated interceptor along a committed flight path."""

    def __init__(self, *, speed: float = 0.85) -> None:
        self.speed = speed
        self._reset_state()

    def _reset_state(self) -> None:
        self._active = False
        self._launched_at: float | None = None
        self._launch_point = Point(x=0.5, y=1.0)
        self._aim_point: Point | None = None
        self._flight_time = 0.0
        self._trail: list[Point] = []
        self._phase = InterceptorPhase.IDLE

    def reset(self) -> None:
        self._reset_state()

    @property
    def active(self) -> bool:
        return self._active

    def launch(
        self, solution: InterceptSolution | None, now: float
    ) -> InterceptSolution | None:
        """Commit a flight. Returns the solution actually flown.

        If no feasible intercept exists the interceptor is still launched —
        the operator authorized an engagement and must see it happen — but it
        flies to the last predicted position and is reported as a miss rather
        than silently pretending to succeed.
        """
        self._launch_point = (
            solution.launch_point if solution and solution.launch_point else Point(x=0.5, y=1.0)
        )

        aim = solution.point if solution and solution.feasible and solution.point else None
        if aim is None:
            # Nothing credible to aim at: fly straight up so the launch is
            # still visible, and report it honestly.
            aim = Point(x=self._launch_point.x, y=max(0.0, self._launch_point.y - 0.6))

        self._aim_point = aim
        distance = math.hypot(aim.x - self._launch_point.x, aim.y - self._launch_point.y)
        self._flight_time = distance / self.speed if self.speed > 0 else 0.0
        self._launched_at = now
        self._active = True
        self._phase = InterceptorPhase.LAUNCH
        self._trail = [self._launch_point]

        log.info(
            "Interceptor launched (simulated) toward (%.3f, %.3f), flight %.2fs",
            aim.x,
            aim.y,
            self._flight_time,
        )
        return solution

    def update(self, now: float) -> InterceptorState:
        """Advance the simulation and return the current state."""
        if not self._active or self._launched_at is None or self._aim_point is None:
            return InterceptorState(phase=InterceptorPhase.IDLE, active=False)

        elapsed = now - self._launched_at

        if elapsed < LAUNCH_PHASE:
            self._phase = InterceptorPhase.LAUNCH
            position = self._launch_point
            progress = 0.0
        else:
            flight_elapsed = elapsed - LAUNCH_PHASE
            progress = (
                min(1.0, flight_elapsed / self._flight_time) if self._flight_time > 0 else 1.0
            )
            position = Point(
                x=self._launch_point.x + (self._aim_point.x - self._launch_point.x) * progress,
                y=self._launch_point.y + (self._aim_point.y - self._launch_point.y) * progress,
            )

            if progress >= 1.0:
                self._phase = (
                    InterceptorPhase.INTERCEPT
                    if flight_elapsed - self._flight_time < INTERCEPT_PHASE
                    else InterceptorPhase.SPENT
                )
            else:
                self._phase = InterceptorPhase.FLIGHT

            if not self._trail or _distance(self._trail[-1], position) > 0.004:
                self._trail.append(position)
                del self._trail[:-TRAIL_LENGTH]

        remaining = max(0.0, (LAUNCH_PHASE + self._flight_time) - elapsed)

        return InterceptorState(
            phase=self._phase,
            active=True,
            position=position,
            launch_point=self._launch_point,
            aim_point=self._aim_point,
            trail=list(self._trail),
            progress=round(progress, 4),
            time_since_launch=round(elapsed, 3),
            time_to_intercept=round(remaining, 3),
        )


def _distance(a: Point, b: Point) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)
