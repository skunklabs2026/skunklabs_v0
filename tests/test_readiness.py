"""Engagement readiness — the gate immediately upstream of the launcher."""

from __future__ import annotations

import pytest

from backend.mission.readiness import (
    AUTHORIZATION_VALID,
    CANISTER_OPERATIONAL,
    CONDITION_ORDER,
    LAUNCHER_INTERFACE_READY,
    TARGET_VALID,
    TRACK_CONFIRMED,
    TRACK_STABLE,
    EngagementReadinessEvaluator,
    ReadinessInputs,
)
from backend.schemas import MissionState, ReadinessState, SubsystemState


@pytest.fixture
def evaluator() -> EngagementReadinessEvaluator:
    return EngagementReadinessEvaluator(min_track_stability=0.25)


def ready_inputs(**overrides) -> ReadinessInputs:
    """Inputs where every precondition is met but nobody has authorized yet."""
    base = dict(
        mission_state=MissionState.FOLLOWING,
        target_id="UAV-001",
        track_confirmed=True,
        track_stability=0.8,
        track_duration=4.0,
        canister_state=SubsystemState.OPERATIONAL,
        launcher_ready=True,
        launch_command_issued=False,
    )
    base.update(overrides)
    return ReadinessInputs(**base)


class TestConditions:
    def test_every_condition_is_reported(self, evaluator):
        """All six conditions appear whatever the verdict — the panel is fixed."""
        report = evaluator.evaluate(ready_inputs())
        assert [c.name for c in report.conditions] == list(CONDITION_ORDER)

    def test_ready_when_preconditions_met(self, evaluator):
        report = evaluator.evaluate(ready_inputs())
        assert report.state is ReadinessState.READY_FOR_AUTHORIZATION
        # Authorization is the only outstanding condition, by design.
        assert report.blocking == [AUTHORIZATION_VALID]

    def test_no_target_is_not_ready(self, evaluator):
        report = evaluator.evaluate(
            ready_inputs(target_id=None, mission_state=MissionState.SEARCHING)
        )
        assert report.state is ReadinessState.NOT_READY
        assert TARGET_VALID in report.blocking

    def test_criteria_not_met_is_not_ready(self, evaluator):
        """A track exists but has not satisfied the demo rules."""
        report = evaluator.evaluate(ready_inputs(mission_state=MissionState.TRACKING))
        assert report.state is ReadinessState.NOT_READY
        assert TARGET_VALID in report.blocking

    def test_unconfirmed_track_is_not_ready(self, evaluator):
        report = evaluator.evaluate(ready_inputs(track_confirmed=False))
        assert report.state is ReadinessState.NOT_READY
        assert TRACK_CONFIRMED in report.blocking

    def test_unstable_track_is_not_ready(self, evaluator):
        report = evaluator.evaluate(ready_inputs(track_stability=0.05))
        assert report.state is ReadinessState.NOT_READY
        assert TRACK_STABLE in report.blocking

    def test_stability_threshold_is_inclusive(self, evaluator):
        assert evaluator.evaluate(ready_inputs(track_stability=0.25)).state is (
            ReadinessState.READY_FOR_AUTHORIZATION
        )

    def test_offline_canister_is_not_ready(self, evaluator):
        report = evaluator.evaluate(ready_inputs(canister_state=SubsystemState.OFFLINE))
        assert report.state is ReadinessState.NOT_READY
        assert CANISTER_OPERATIONAL in report.blocking

    def test_degraded_canister_may_still_engage(self, evaluator):
        """DEGRADED is a warning, not a stop — a slow frame rate is not a fault."""
        report = evaluator.evaluate(ready_inputs(canister_state=SubsystemState.DEGRADED))
        assert report.state is ReadinessState.READY_FOR_AUTHORIZATION

    def test_missing_launcher_is_not_ready(self, evaluator):
        report = evaluator.evaluate(ready_inputs(launcher_ready=False))
        assert report.state is ReadinessState.NOT_READY
        assert LAUNCHER_INTERFACE_READY in report.blocking

    def test_blocking_condition_is_named_in_the_detail(self, evaluator):
        """ "Not ready" must always say which condition failed."""
        report = evaluator.evaluate(ready_inputs(launcher_ready=False))
        assert LAUNCHER_INTERFACE_READY in report.detail


class TestDerivedState:
    def test_authorized_after_operator_action(self, evaluator):
        report = evaluator.evaluate(ready_inputs(mission_state=MissionState.AUTHORIZED))
        assert report.state is ReadinessState.AUTHORIZED
        assert report.blocking == []

    def test_launch_command_issued_is_terminal(self, evaluator):
        report = evaluator.evaluate(
            ready_inputs(mission_state=MissionState.ACTUATED, launch_command_issued=True)
        )
        assert report.state is ReadinessState.LAUNCH_COMMAND_ISSUED

    def test_target_loss_after_authorization_does_not_revoke_it(self, evaluator):
        """The decision was taken while the target was valid; it stands.

        Re-testing the target here would retroactively invalidate an
        authorization the operator has already given.
        """
        report = evaluator.evaluate(
            ready_inputs(
                mission_state=MissionState.AUTHORIZED,
                target_id=None,
                track_confirmed=False,
                track_stability=0.0,
            )
        )
        assert report.state is ReadinessState.AUTHORIZED

    def test_readiness_never_authorizes_on_its_own(self, evaluator):
        """No combination of healthy hardware produces AUTHORIZED by itself."""
        for state in (MissionState.FOLLOWING, MissionState.AWAITING_AUTHORIZATION):
            report = evaluator.evaluate(ready_inputs(mission_state=state))
            assert report.state is ReadinessState.READY_FOR_AUTHORIZATION
