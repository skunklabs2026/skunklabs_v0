"""Trajectory prediction and intercept estimation.

Two deliberately simple, deterministic pieces of maths:

  TrajectoryPredictor  Fits recent observed motion and extrapolates a short
                       distance forward.

  InterceptSolver      Given that extrapolation and a notional interceptor
                       speed, finds the earliest point where the two could
                       meet.

>>> SCOPE <<<
This works entirely in the *image plane*, in normalised (0..1) frame
coordinates. It is a kinematic extrapolation of pixel motion for display, not
a flight model, not a guidance law, and not a firing solution. There is no
range, no altitude, no camera calibration and no 3D. Nothing in the system
acts on the output - it drives an on-screen prediction and a simulated
animation. See README, "What V0 is not".

Why a constant-acceleration least-squares fit rather than a Kalman filter:
the input is a short, clean history of a single target, the model has to be
inspectable to be trustworthy in a demo, and the fit residual falls out for
free as a confidence signal. A filter would add tuning surface without
improving a two-second horizon.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from backend.schemas import (
    InterceptSolution,
    Point,
    Trajectory,
    TrajectoryPoint,
    Velocity,
)
from backend.vision.tracker import Track

# Minimum observations before any extrapolation is attempted. Below this a
# "prediction" is just noise amplification.
MIN_HISTORY = 6


@dataclass(frozen=True)
class Observation:
    """One observed centre position at a moment in time, normalised."""

    t: float
    x: float
    y: float


class TrajectoryPredictor:
    """Extrapolates a target's recent image-plane motion.

    Fits x(t) and y(t) independently as quadratics using least squares over
    the most recent window, then samples the fit forward. A quadratic captures
    the gentle curvature of a drone crossing the frame without the wild
    divergence a higher-order fit produces the moment it extrapolates.
    """

    def __init__(
        self,
        *,
        horizon: float = 2.0,
        samples: int = 16,
        window: int = 24,
        max_residual: float = 0.02,
    ) -> None:
        self.horizon = horizon
        self.samples = samples
        self.window = window
        self.max_residual = max_residual

    def predict(
        self,
        observations: list[Observation],
        *,
        horizon_scale: float = 1.0,
        confidence_scale: float = 1.0,
    ) -> Trajectory:
        """Extrapolate forward from `observations` (oldest first).

        `horizon_scale` and `confidence_scale` come from the platform
        classification. A fixed-wing holds its course, so we predict further
        ahead and trust it more; a multirotor can turn on the spot, so the
        horizon shortens and confidence drops. Extrapolating a quad as far as
        a cruise missile would draw a confident line to nowhere.
        """
        horizon = max(0.2, self.horizon * horizon_scale)

        if len(observations) < MIN_HISTORY:
            return Trajectory(valid=False, horizon=horizon)

        recent = observations[-self.window :]
        t0 = recent[-1].t  # predict relative to the newest observation
        ts = np.array([o.t - t0 for o in recent], dtype=float)
        xs = np.array([o.x for o in recent], dtype=float)
        ys = np.array([o.y for o in recent], dtype=float)

        # A stationary or near-stationary target has no meaningful heading;
        # extrapolating one produces a jittering prediction.
        span = math.hypot(xs[-1] - xs[0], ys[-1] - ys[0])
        if span < 1e-3:
            return Trajectory(valid=False, horizon=horizon)

        # Degree 2 needs at least 3 distinct samples; fall back to linear.
        degree = 2 if len(recent) >= 8 else 1
        try:
            cx = np.polyfit(ts, xs, degree)
            cy = np.polyfit(ts, ys, degree)
        except (np.linalg.LinAlgError, ValueError):
            return Trajectory(valid=False, horizon=horizon)

        # Residual over the fitted window is our honesty check: a track that
        # is being extrapolated badly says so rather than drawing a confident
        # wrong line.
        residual = float(
            np.mean(
                np.hypot(np.polyval(cx, ts) - xs, np.polyval(cy, ts) - ys),
            )
        )

        dx = float(np.polyval(np.polyder(cx), 0.0))
        dy = float(np.polyval(np.polyder(cy), 0.0))
        speed = math.hypot(dx, dy)

        points = [
            TrajectoryPoint(
                x=float(np.polyval(cx, dt)),
                y=float(np.polyval(cy, dt)),
                t=float(dt),
            )
            for dt in np.linspace(horizon / self.samples, horizon, self.samples)
        ]

        # Confidence blends fit quality with how much history backs it.
        fit_quality = max(0.0, 1.0 - residual / self.max_residual)
        history_quality = min(1.0, len(recent) / float(self.window))
        confidence = float(
            max(
                0.0,
                min(
                    1.0,
                    (fit_quality * 0.75 + history_quality * 0.25) * confidence_scale,
                ),
            )
        )

        return Trajectory(
            valid=True,
            points=points,
            velocity=Velocity(x=dx, y=dy, speed=speed),
            residual=residual,
            confidence=confidence,
            horizon=horizon,
        )

    @staticmethod
    def observations_from_track(
        track: Track,
        *,
        frame_width: int,
        frame_height: int,
        now: float,
        fps: float,
    ) -> list[Observation]:
        """Build a normalised observation history from a track's trail.

        The trail stores positions but not timestamps, so times are
        reconstructed backwards from `now` at the frame interval. Over a
        one-second window at a steady frame rate this is accurate enough for
        a two-second extrapolation, and it avoids widening the tracker's
        interface for a display feature.
        """
        if frame_width <= 0 or frame_height <= 0 or not track.trail:
            return []

        dt = 1.0 / fps if fps > 0 else 0.04
        trail = list(track.trail)
        count = len(trail)
        return [
            Observation(
                t=now - (count - 1 - i) * dt,
                x=cx / float(frame_width),
                y=cy / float(frame_height),
            )
            for i, (cx, cy) in enumerate(trail)
        ]


class InterceptSolver:
    """Estimates where a notional interceptor could meet the target.

    Walks the predicted trajectory and finds the earliest sample the
    interceptor could reach in time, given a constant speed from a fixed
    launch point. This is the classic "can I get there before it does"
    check, solved by sampling rather than algebraically - the trajectory is
    already a discrete set of points, and sampling handles the curved fit
    without a closed-form solution.

    Purely for display. Nothing is commanded from this result.
    """

    def __init__(
        self,
        *,
        launch_point: tuple[float, float] = (0.5, 1.0),
        interceptor_speed: float = 0.85,
        min_confidence: float = 0.25,
    ) -> None:
        self.launch_point = launch_point
        self.interceptor_speed = interceptor_speed
        self.min_confidence = min_confidence

    def solve(self, trajectory: Trajectory) -> InterceptSolution:
        launch = Point(x=self.launch_point[0], y=self.launch_point[1])

        if not trajectory.valid or not trajectory.points:
            return InterceptSolution(
                feasible=False, launch_point=launch, detail="No usable trajectory."
            )

        if trajectory.confidence < self.min_confidence:
            return InterceptSolution(
                feasible=False,
                launch_point=launch,
                detail=f"Trajectory confidence {trajectory.confidence:.0%} below threshold.",
            )

        for point in trajectory.points:
            distance = math.hypot(point.x - launch.x, point.y - launch.y)
            flight_time = distance / self.interceptor_speed
            # The interceptor must arrive no later than the target does.
            if flight_time <= point.t:
                return InterceptSolution(
                    feasible=True,
                    point=Point(x=point.x, y=point.y),
                    time_to_intercept=round(point.t, 3),
                    launch_point=launch,
                    detail=f"Intercept in {point.t:.1f}s.",
                )

        return InterceptSolution(
            feasible=False,
            launch_point=launch,
            detail="No intercept within the prediction horizon.",
        )


def build_trajectory_predictor(settings) -> TrajectoryPredictor:
    return TrajectoryPredictor(
        horizon=settings.trajectory_horizon,
        samples=settings.trajectory_samples,
        window=settings.trajectory_window,
        max_residual=settings.trajectory_max_residual,
    )


def build_intercept_solver(settings) -> InterceptSolver:
    return InterceptSolver(
        launch_point=(settings.launch_point_x, settings.launch_point_y),
        interceptor_speed=settings.interceptor_speed,
        min_confidence=settings.intercept_min_confidence,
    )
