"""Engagement: tracks in, mission decisions out.

One role: decide what the tracks *mean*, and carry that decision as far as the
launcher boundary - no further.

    tracks
      → target designation
      → airframe classification
      → sensor-frame projection
      → MISSION STATE MACHINE
      → ENGAGEMENT READINESS
      → operator authorization
      → LAUNCH COMMAND
      → safe actuator interface

The last three arrows are the point of this stage. Readiness is evaluated
before the state machine advances (so the machine can refuse to offer a
control the canister could not honour) and again after (so telemetry reports
the readiness that matches the state the operator is looking at).

This stage never touches pixels and never reads a video source.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.actuation.base import ActuatorInterface, build_launch_command
from backend.actuation.interceptor import InterceptorSimulation
from backend.actuation.simulated import build_actuator
from backend.config.settings import Settings
from backend.mission.classification import build_platform_classifier, profile_for
from backend.mission.projection import build_track_projection
from backend.mission.readiness import ReadinessInputs, build_readiness_evaluator
from backend.mission.rules import build_rule_engine
from backend.mission.speed import build_speed_estimator
from backend.mission.state_machine import MissionConfig, MissionStateMachine
from backend.mission.trajectory import (
    TrajectoryPredictor,
    build_intercept_solver,
    build_trajectory_predictor,
)
from backend.schemas import (
    EngagementReadiness,
    EventCode,
    EventKind,
    InterceptorState,
    InterceptSolution,
    LaunchAcknowledgement,
    LaunchCommand,
    LauncherStatus,
    MissionState,
    MissionStatus,
    PlatformClass,
    ReadinessState,
    SubsystemState,
    Target,
)
from backend.targets.target_manager import TargetManager


class EventEmitter(Protocol):
    """How this stage reports to the operator.

    Injected rather than imported, so engagement has no dependency on the
    telemetry hub and can be tested with a list.
    """

    def __call__(
        self,
        kind: EventKind,
        message: str,
        *,
        code: EventCode = ...,
        target_id: str | None = ...,
    ) -> object: ...


@dataclass(slots=True)
class EngagementResult:
    """Everything the engagement stage produces for one frame."""

    mission: MissionStatus
    targets: list[Target]
    readiness: EngagementReadiness
    launcher: LauncherStatus
    intercept: InterceptSolution | None
    interceptor: InterceptorState | None


class EngagementStage:
    """The mission controller.

    Owns designation, classification, projection, the mission state machine,
    the engagement-readiness gate and the launcher boundary.
    """

    def __init__(self, settings: Settings, emit: EventEmitter) -> None:
        self.settings = settings
        self._emit = emit

        self.targets = TargetManager()
        self.classifier = build_platform_classifier(settings)
        self.speed_estimator = build_speed_estimator(settings)
        self.predictor = build_trajectory_predictor(settings)
        self.intercept_solver = build_intercept_solver(settings)
        self.interceptor = InterceptorSimulation(speed=settings.interceptor_speed)

        # The launcher boundary. Typed as the interface, never as the concrete
        # class, so a hardware controller can be dropped in behind it.
        self.actuator: ActuatorInterface = build_actuator(settings)
        self.readiness_evaluator = build_readiness_evaluator(settings)

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

        # Latest readiness verdict, so the API can report it on a command reply
        # without re-deriving it.
        self.readiness = EngagementReadiness()

        # Latest intercept estimate, and the one committed at launch.
        self.intercept: InterceptSolution | None = None
        self._committed_intercept: InterceptSolution | None = None

        # Launch bookkeeping for the current engagement.
        self._launch_command: LaunchCommand | None = None
        self._launch_acknowledgement: LaunchAcknowledgement | None = None
        # Canister health, pushed in by the pipeline each frame. Readiness is
        # a property of the whole canister, not of this stage alone.
        self._canister_state = SubsystemState.INITIALISING
        self._canister_detail = ""
        # Raised once per launch so the recorder can capture it exactly once.
        self._launch_record: tuple[LaunchCommand, LaunchAcknowledgement] | None = None

    # ------------------------------------------------------------------
    # Canister health input
    # ------------------------------------------------------------------

    def set_canister_health(self, state: SubsystemState, detail: str) -> None:
        """Supply the canister roll-up used by the readiness gate."""
        self._canister_state = state
        self._canister_detail = detail

    # ------------------------------------------------------------------
    # Per-frame evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self, tracks: list, *, width: int, height: int, now: float, fps: float
    ) -> EngagementResult:
        """Advance the mission by one frame."""
        primary = self.targets.select_primary(tracks)
        designation = self._designate(primary) if primary is not None else None

        self._observe_for_classification(tracks, width=width, height=height, now=now)

        trajectory = self._predict(primary, width=width, height=height, now=now, fps=fps)
        projection = build_track_projection(trajectory)

        # ---- readiness gate, evaluated *before* the machine advances ----
        # The machine may not offer the authorization control unless every
        # precondition other than the authorization itself already holds.
        pre = self._evaluate_readiness(primary, projection, now=now)
        gate_open = pre.state is not ReadinessState.NOT_READY

        engaged_track_id = primary.track_id if primary is not None else None
        mission_status = self.mission.update(
            primary,
            designation,
            now=now,
            engagement_ready=gate_open,
            readiness_detail=pre.detail,
        )

        # Retire the engaged track so the mission does not instantly re-arm
        # on the target it just engaged.
        if self.mission.consume_engagement_complete() and engaged_track_id is not None:
            self.targets.mark_engaged(engaged_track_id)

        if self.mission.should_dispatch_actuation():
            self._issue_launch_command(mission_status, now)

        self._retire_spent_interceptor(mission_status.state)
        self.actuator_update(now)
        interceptor_state = self.interceptor.update(now)

        # ---- readiness re-evaluated, so telemetry matches the new state ----
        self.readiness = self._evaluate_readiness(primary, projection, now=now)

        targets = self.targets.to_targets(
            tracks,
            frame_width=width,
            frame_height=height,
            now=now,
            primary_track_id=self.targets.primary_track_id,
        )
        self._annotate_primary(targets, primary, trajectory, projection)

        return EngagementResult(
            mission=mission_status,
            targets=targets,
            readiness=self.readiness,
            launcher=self.actuator.status(now),
            intercept=self.intercept,
            interceptor=interceptor_state,
        )

    def actuator_update(self, now: float) -> None:
        """Let the launcher interface advance its own handshake timers."""
        update = getattr(self.actuator, "update", None)
        if callable(update):
            update(now)

    def _designate(self, primary) -> str:
        """Assign or recall this track's operator designation.

        A first designation is a reportable event - it is the moment the
        canister stops seeing "an object" and starts holding "UAV-001".
        """
        known = self.targets.has_designation(primary.track_id)
        designation = self.targets.designation_for(primary.track_id, primary.object_class)
        if not known:
            self._emit(
                EventKind.TRACK,
                f"Track created: {designation}.",
                code=EventCode.TRACK_CREATED,
                target_id=designation,
            )
        return designation

    # ------------------------------------------------------------------
    # Readiness
    # ------------------------------------------------------------------

    def _evaluate_readiness(self, primary, projection, *, now: float) -> EngagementReadiness:
        return self.readiness_evaluator.evaluate(
            ReadinessInputs(
                mission_state=self.mission.state,
                target_id=self.mission.target_id,
                track_confirmed=bool(primary is not None and primary.confirmed),
                track_stability=projection.confidence if projection.valid else 0.0,
                track_duration=primary.duration(now) if primary is not None else 0.0,
                canister_state=self._canister_state,
                canister_detail=self._canister_detail,
                launcher_ready=self.actuator.ready,
                launcher_detail=self.actuator.status(now).detail,
                launch_command_issued=self._launch_command is not None,
            )
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
        """Extrapolate the primary target's path in the sensor frame.

        Display and track-stability only - the mission state machine consumes
        no geometry from here, and nothing physical acts on it.
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

    # ------------------------------------------------------------------
    # The launcher boundary
    # ------------------------------------------------------------------

    def _issue_launch_command(self, mission_status: MissionStatus, now: float) -> None:
        """Mint a launch command, hand it across the boundary, log the reply.

        Called exactly once per authorization - the one-shot latch lives in
        the state machine, so this is safe to call on every frame that reports
        a pending dispatch.

        >>> SAFETY <<< The command is delivered to a simulated interface. It
        produces a log entry, a telemetry event and an animation.
        """
        command = build_launch_command(
            target_id=mission_status.target_id,
            mission_state=mission_status.state,
            readiness=ReadinessState.AUTHORIZED,
            # The operator's own timestamp, not this frame's - the two differ
            # by a frame, and the gap between them is exactly the latency a
            # field test measures.
            authorized_at=self.mission.authorized_at or now,
            issued_at=now,
        )
        self._launch_command = command
        self._emit(
            EventKind.ACTUATION,
            f"Launch command {command.command_id} issued for "
            f"{command.target_id or 'unknown target'} (simulated).",
            code=EventCode.LAUNCH_COMMAND_ISSUED,
            target_id=command.target_id,
        )

        acknowledgement = self.actuator.execute(command)
        self._launch_acknowledgement = acknowledgement
        self._launch_record = (command, acknowledgement)

        self._emit(
            EventKind.ACTUATION if acknowledgement.accepted else EventKind.ERROR,
            (
                f"Launcher acknowledged {acknowledgement.command_id} in "
                f"{acknowledgement.latency_ms:.0f} ms. {acknowledgement.detail}"
                if acknowledgement.accepted
                else f"Launcher REJECTED {acknowledgement.command_id}. {acknowledgement.detail}"
            ),
            code=(
                EventCode.ACTUATOR_ACKNOWLEDGED
                if acknowledgement.accepted
                else EventCode.ACTUATOR_REJECTED
            ),
            target_id=command.target_id,
        )

        # Freeze the projection as it stood at the moment of launch. The
        # simulated interceptor flies a committed path and is never re-aimed.
        self._committed_intercept = self.intercept
        self.interceptor.launch(self._committed_intercept, now)

    def consume_launch_record(
        self,
    ) -> tuple[LaunchCommand, LaunchAcknowledgement] | None:
        """Return the launch command and its acknowledgement, exactly once.

        The mission recorder uses this; a one-shot latch keeps a single
        engagement from being written into a report repeatedly.
        """
        record = self._launch_record
        self._launch_record = None
        return record

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

    def _annotate_primary(self, targets: list[Target], primary, trajectory, projection) -> None:
        """Attach projection, airframe and speed to the primary target only.

        A trajectory drawn per box would be unreadable.
        """
        for target in targets:
            if not target.is_primary:
                continue

            if trajectory is not None and trajectory.valid:
                target.trajectory = trajectory
            target.projection = projection

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
        """Advance the mission with no target - used while the sensor is down."""
        return self.mission.update(None, None, engagement_ready=False)

    def launcher_status(self, now: float | None = None) -> LauncherStatus:
        return self.actuator.status(now)

    def reset(self, *, reason: str = "Operator reset") -> None:
        """Clear designation, classification and engagement state."""
        self.mission.reset(reason=reason)
        self.targets.reset()
        self.classifier.reset()
        self.actuator.reset()
        self.interceptor.reset()
        self.intercept = None
        self._committed_intercept = None
        self._launch_command = None
        self._launch_acknowledgement = None
        self._launch_record = None
        self.readiness = EngagementReadiness()
