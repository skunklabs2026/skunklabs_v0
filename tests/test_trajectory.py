"""Trajectory prediction, intercept estimation and interceptor simulation."""

from __future__ import annotations

import math

import pytest

from backend.actuation.interceptor import InterceptorSimulation
from backend.mission.trajectory import (
    InterceptSolver,
    Observation,
    TrajectoryPredictor,
)
from backend.schemas import InterceptorPhase, InterceptSolution, Point


def straight_line(
    *, n: int = 24, dt: float = 0.04, vx: float = 0.2, vy: float = -0.1
) -> list[Observation]:
    """A target moving at constant velocity."""
    return [
        Observation(t=i * dt, x=0.1 + vx * (i * dt), y=0.8 + vy * (i * dt)) for i in range(n)
    ]


class TestTrajectoryPredictor:
    def test_rejects_short_history(self):
        predictor = TrajectoryPredictor()
        assert not predictor.predict(straight_line(n=3)).valid

    def test_rejects_stationary_target(self):
        """A stationary object has no heading worth extrapolating."""
        predictor = TrajectoryPredictor()
        observations = [Observation(t=i * 0.04, x=0.5, y=0.5) for i in range(24)]
        assert not predictor.predict(observations).valid

    def test_predicts_constant_velocity(self):
        """A straight line must extrapolate to the right place."""
        predictor = TrajectoryPredictor(horizon=1.0, samples=10)
        trajectory = predictor.predict(straight_line(vx=0.2, vy=-0.1))

        assert trajectory.valid
        last_observation = straight_line()[-1]
        final = trajectory.points[-1]

        assert final.t == pytest.approx(1.0, abs=1e-6)
        assert final.x == pytest.approx(last_observation.x + 0.2, abs=0.01)
        assert final.y == pytest.approx(last_observation.y - 0.1, abs=0.01)

    def test_recovers_velocity(self):
        predictor = TrajectoryPredictor()
        trajectory = predictor.predict(straight_line(vx=0.2, vy=-0.1))
        assert trajectory.velocity is not None
        assert trajectory.velocity.x == pytest.approx(0.2, abs=0.02)
        assert trajectory.velocity.y == pytest.approx(-0.1, abs=0.02)
        assert trajectory.velocity.speed == pytest.approx(math.hypot(0.2, 0.1), abs=0.02)

    def test_clean_track_is_high_confidence(self):
        trajectory = TrajectoryPredictor().predict(straight_line())
        assert trajectory.confidence > 0.8
        assert trajectory.residual < 0.001

    def test_noisy_track_lowers_confidence(self):
        """A jittery track must report lower confidence, not a confident lie."""
        import random

        random.seed(11)
        noisy = [
            Observation(
                t=o.t, x=o.x + random.uniform(-0.03, 0.03), y=o.y + random.uniform(-0.03, 0.03)
            )
            for o in straight_line()
        ]
        clean_conf = TrajectoryPredictor().predict(straight_line()).confidence
        noisy_conf = TrajectoryPredictor().predict(noisy).confidence
        assert noisy_conf < clean_conf

    def test_horizon_is_respected(self):
        trajectory = TrajectoryPredictor(horizon=3.0, samples=12).predict(straight_line())
        assert trajectory.points[-1].t == pytest.approx(3.0, abs=1e-6)
        assert len(trajectory.points) == 12


class TestInterceptSolver:
    def test_no_solution_for_invalid_trajectory(self):
        from backend.schemas import Trajectory

        solution = InterceptSolver().solve(Trajectory(valid=False))
        assert not solution.feasible
        assert solution.launch_point is not None

    def test_finds_intercept_for_approaching_target(self):
        """A target crossing near the launcher is interceptable."""
        predictor = TrajectoryPredictor(horizon=3.0)
        # Moving toward the bottom-centre launch point.
        observations = [
            Observation(t=i * 0.04, x=0.2 + 0.1 * (i * 0.04), y=0.3 + 0.1 * (i * 0.04))
            for i in range(24)
        ]
        solution = InterceptSolver(interceptor_speed=1.5).solve(predictor.predict(observations))
        assert solution.feasible
        assert solution.point is not None
        assert solution.time_to_intercept > 0

    def test_too_slow_interceptor_has_no_solution(self):
        predictor = TrajectoryPredictor(horizon=1.0)
        solution = InterceptSolver(interceptor_speed=0.01).solve(
            predictor.predict(straight_line())
        )
        assert not solution.feasible
        assert "horizon" in solution.detail.lower()

    def test_low_confidence_blocks_solution(self):
        """A prediction we do not trust must not yield a firing estimate."""
        from backend.schemas import Trajectory, TrajectoryPoint

        trajectory = Trajectory(
            valid=True,
            points=[TrajectoryPoint(x=0.5, y=0.5, t=1.0)],
            confidence=0.05,
        )
        solution = InterceptSolver(min_confidence=0.25).solve(trajectory)
        assert not solution.feasible
        assert "confidence" in solution.detail.lower()

    def test_solution_is_deterministic(self):
        predictor = TrajectoryPredictor()
        solver = InterceptSolver(interceptor_speed=1.5)
        trajectory = predictor.predict(straight_line())
        results = {
            (s.feasible, s.time_to_intercept)
            for s in (solver.solve(trajectory) for _ in range(10))
        }
        assert len(results) == 1


class TestInterceptorSimulation:
    def _solution(self) -> InterceptSolution:
        return InterceptSolution(
            feasible=True,
            point=Point(x=0.5, y=0.4),
            time_to_intercept=1.0,
            launch_point=Point(x=0.5, y=1.0),
        )

    def test_idle_before_launch(self):
        state = InterceptorSimulation().update(1_000.0)
        assert state.phase is InterceptorPhase.IDLE
        assert not state.active

    def test_launch_then_flight_then_intercept(self):
        sim = InterceptorSimulation(speed=0.6)
        sim.launch(self._solution(), 1_000.0)

        assert sim.update(1_000.1).phase is InterceptorPhase.LAUNCH
        assert sim.update(1_000.6).phase is InterceptorPhase.FLIGHT

        # Distance 0.6 at speed 0.6 = 1.0s flight, after a 0.25s launch phase.
        arrived = sim.update(1_001.3)
        assert arrived.phase is InterceptorPhase.INTERCEPT
        assert arrived.progress == pytest.approx(1.0)

    def test_reaches_the_aim_point(self):
        sim = InterceptorSimulation(speed=0.6)
        sim.launch(self._solution(), 1_000.0)
        state = sim.update(1_001.3)
        assert state.position is not None
        assert state.position.x == pytest.approx(0.5, abs=1e-6)
        assert state.position.y == pytest.approx(0.4, abs=1e-6)

    def test_aim_point_is_frozen_at_launch(self):
        """The interceptor commits; it is never re-aimed mid-flight."""
        sim = InterceptorSimulation(speed=0.6)
        sim.launch(self._solution(), 1_000.0)
        first = sim.update(1_000.5).aim_point

        # A new (ignored) solution arriving later must not move the aim point.
        later = sim.update(1_001.0).aim_point
        assert first == later

    def test_launches_without_a_solution(self):
        """An authorized engagement is always shown, even with no solution."""
        sim = InterceptorSimulation()
        sim.launch(None, 1_000.0)
        state = sim.update(1_000.5)
        assert state.active
        assert state.aim_point is not None

    def test_infeasible_solution_still_launches(self):
        sim = InterceptorSimulation()
        sim.launch(InterceptSolution(feasible=False, launch_point=Point(x=0.5, y=1.0)), 1_000.0)
        assert sim.update(1_000.5).active

    def test_reset_returns_to_idle(self):
        sim = InterceptorSimulation()
        sim.launch(self._solution(), 1_000.0)
        sim.reset()
        assert sim.update(1_001.0).phase is InterceptorPhase.IDLE

    def test_trail_accumulates_during_flight(self):
        sim = InterceptorSimulation(speed=0.6)
        sim.launch(self._solution(), 1_000.0)
        for i in range(1, 25):
            state = sim.update(1_000.0 + i * 0.05)
        assert len(state.trail) > 3
