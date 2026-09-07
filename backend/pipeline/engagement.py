"""Engagement: tracks in, mission decisions out.

One role: decide what the tracks *mean*. Target designation, airframe
classification, trajectory prediction, the intercept estimate, the mission
state machine and the (simulated) actuator all live here.

This stage never touches pixels and never reads a video source. It is given
a track list plus the frame geometry that track coordinates are expressed
in, and returns everything the UI needs to render the mission.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.actuation.base import ActuatorInterface
from backend.actuation.interceptor import InterceptorSimulation
from backend.actuation.simulated import build_actuator
from backend.config.settings import Settings
from backend.mission.classification import build_platform_classifier, profile_for
from backend.mission.rules import build_rule_engine
from backend.mission.speed import build_speed_estimator
from backend.mission.state_machine import MissionConfig, MissionStateMachine
from backend.mission.trajectory import (
    TrajectoryPredictor,
    build_intercept_solver,
    build_trajectory_predictor,
)
from backend.schemas import (
    EventKind,
    InterceptorState,
    InterceptSolution,
    MissionState,
    MissionStatus,
    PlatformClass,
    Target,
)
from backend.targets.target_manager import TargetManager


class EventEmitter(Protocol):
    """How this stage reports to the operator.

    Injected rather than imported, so engagement has no dependency on the
    telemetry hub and can be tested with a list.
    """

    def __call__(self, kind: EventKind, message: str) -> object: ...


@dataclass(slots=True)
class EngagementResult:
    """Everything the engagement stage produces for one frame."""

    mission: MissionStatus
    targets: list[Target]
    intercept: InterceptSolution | None
    interceptor: InterceptorState | None


class EngagementStage:
    """Owns designation, classification, prediction and the mission state machine."""

    def __init__(self, settings: Settings, emit: EventEmitter) -> None:
        self.settings = settings
        self._emit = emit

        self.targets = TargetManager()
        self.classifier = build_platform_classifier(settings)
        self.speed_estimator = build_speed_estimator(settings)
        self.predictor = build_trajectory_predictor(settings)
        self.intercept_solver = build_intercept_solver(settings)
        self.interceptor = InterceptorSimulation(speed=settings.interceptor_speed)
        self.actuator: ActuatorInterface = build_actuator(settings)

        self.mission = MissionStateMachine(
            build_rule_engine(settings),
            MissionConfig(
                confirmation_time=settings.confirmation_time,
                follow_time=settings.follow_time,
                target_lost_grace=settings.target_lost_grace,
                target_lost_hold=settings.target_lost_hold,
                actuated_hold=settings.actuated_hold,
                actuator_duration=settings.actuator_duration,
            ),
            emit=emit,
        )

        # Latest intercept estimate, and the one committed at launch.
        self.intercept: InterceptSolution | None = None
        self._committed_intercept: InterceptSolution | None = None

    # ------------------------------------------------------------------
    # Per-frame evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self, tracks: list, *, width: int, height: int, now: float, fps: float
    ) -> EngagementResult:
        """Advance the mission by one frame."""
        primary = self.targets.select_primary(tracks)
        designation = (
            self.targets.designation_for(primary.track_id, primary.object_class)
            if primary is not None
            else None
        )

        self._observe_for_classification(tracks, width=width, height=height, now=now)

        trajectory = self._predict(primary, width=width, height=height, now=now, fps=fps)

        engaged_track_id = primary.track_id if primary is not None else None
        mission_status = self.mission.update(primary, designation, now=now)

        # Retire the engaged track so the mission does not instantly re-arm
        # on the target it just engaged.
        if self.mission.consume_engagement_complete() and engaged_track_id is not None:
            self.targets.mark_engaged(engaged_track_id)

        if self.mission.should_dispatch_actuation():
            self._dispatch_actuation(mission_status, now)

        self._retire_spent_interceptor(mission_status.state)
        interceptor_state = self.interceptor.update(now)

        targets = self.targets.to_targets(
            tracks,
            frame_width=width,
            frame_height=height,
            now=now,
            primary_track_id=self.targets.primary_track_id,
        )
        self._annotate_primary(targets, primary, trajectory)

        return EngagementResult(
            mission=mission_status,
            targets=targets,
            intercept=self.intercept,
            interceptor=interceptor_state,
        )

    def _observe_for_classification(
        self, tracks: list, *, width: int, height: int, now: float
    ) -> None:
        """Feed every confirmed track to the airframe classifier.

        Classification changes how far ahead we predict and what absolute
        speed the observed motion implies, so it has to happen before both.
        """
        if width <= 0 or height <= 0:
            return
        for track in tracks:
            if not track.confirmed:
                continue
            cx, cy = track.center
            self.classifier.observe(
                track.track_id,
                t=now,
                x=cx / width,
                y=cy / height,
                size=track.width / width,
            )

    def _predict(self, primary, *, width: int, height: int, now: float, fps: float):
        """Extrapolate the primary target's path and solve for an intercept.

        Display only — the mission state machine consumes neither result.
        """
        if primary is None:
            self.intercept = None
            return None

        platform, _ = self.classifier.classify(primary.track_id)
        profile = profile_for(platform)
        trajectory = self.predictor.predict(
            TrajectoryPredictor.observations_from_track(
                primary,
                frame_width=width,
                frame_height=height,
                now=now,
                fps=fps or self.settings.target_fps,
            ),
            horizon_scale=profile.horizon_scale,
            confidence_scale=profile.confidence_scale,
        )
        self.intercept = self.intercept_solver.solve(trajectory)
        return trajectory

    def _dispatch_actuation(self, mission_status: MissionStatus, now: float) -> None:
        """Fire the actuator exactly once per authorization.

        The one-shot latch lives in the state machine, so this is safe to
        call on every frame where it reports a pending dispatch.
        """
        result = self.actuator.fire(mission_status.target_id)
        self._emit(
            EventKind.ACTUATION if result.ok else EventKind.ERROR,
            result.detail,
        )

        # Freeze the intercept estimate as it stood at the moment of launch.
        # This is deliberate: the interceptor flies a committed path and is
        # never re-aimed in flight.
        self._committed_intercept = self.intercept
        self.interceptor.launch(self._committed_intercept, now)

        if self._committed_intercept and self._committed_intercept.feasible:
            self._emit(
                EventKind.ACTUATION,
                f"Interceptor away (simulated). {self._committed_intercept.detail}",
            )
        else:
            self._emit(
                EventKind.WARNING,
                "Interceptor away (simulated). No intercept solution — "
                "flight is indicative only.",
            )

    def _retire_spent_interceptor(self, state: MissionState) -> None:
        """Clear a spent interceptor once the mission leaves engagement.

        The state machine's auto-reset does not know about the interceptor,
        so without this the previous run's flight trail stays painted over
        the next target's engagement.
        """
        if self.interceptor.active and state not in (
            MissionState.AUTHORIZED,
            MissionState.ACTUATED,
        ):
            self.interceptor.reset()
            self._committed_intercept = None

    def _annotate_primary(self, targets: list[Target], primary, trajectory) -> None:
        """Attach prediction, airframe and speed to the primary target only.

        A trajectory drawn per box would be unreadable.
        """
        for target in targets:
            if not target.is_primary:
                continue

            if trajectory is not None and trajectory.valid:
                target.trajectory = trajectory

            platform, features = (
                self.classifier.classify(primary.track_id)
                if primary is not None
                else (PlatformClass.UNKNOWN, None)
            )
            profile = profile_for(platform)
            target.platform = platform
            target.platform_label = profile.label
            target.platform_features = features
            target.speed = self.speed_estimator.estimate(
                image_speed=(
                    trajectory.velocity.speed
                    if trajectory is not None and trajectory.velocity
                    else 0.0
                ),
                bbox_width=target.bbox.width,
                platform=platform,
                profile=profile,
            )
            break

    # ------------------------------------------------------------------
    # Operator commands and state
    # ------------------------------------------------------------------

    def authorize(self) -> tuple[bool, str]:
        return self.mission.request_authorization()

    def idle_status(self) -> MissionStatus:
        """Advance the mission with no target — used while the sensor is down."""
        return self.mission.update(None, None)

    def reset(self, *, reason: str = "Operator reset") -> None:
        """Clear designation, classification and engagement state."""
        self.mission.reset(reason=reason)
        self.targets.reset()
        self.classifier.reset()
        self.actuator.reset()
        self.interceptor.reset()
        self.intercept = None
        self._committed_intercept = None
