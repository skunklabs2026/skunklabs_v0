"""Mission state machine tests.

These cover the transitions the demo depends on, and - more importantly -
the safety interlocks: actuation must be impossible without an explicit
operator authorization taken at the right moment.
"""

from __future__ import annotations

import pytest

from backend.schemas import MissionState
from tests.conftest import make_track


def drive_to_awaiting_authorization(machine, clock):
    """Advance a machine to AWAITING_AUTHORIZATION and return the track."""
    track = make_track(first_seen=clock.now)

    machine.update(track, "UAV-001", now=clock.now)  # SEARCHING -> DETECTED
    machine.update(track, "UAV-001", now=clock.now)  # DETECTED -> TRACKING

    # Satisfy the dwell rule.
    clock.advance(2.1)
    machine.update(track, "UAV-001", now=clock.now)  # -> THREAT_CONFIRMED

    clock.advance(0.9)
    machine.update(track, "UAV-001", now=clock.now)  # -> FOLLOWING

    clock.advance(1.6)
    machine.update(track, "UAV-001", now=clock.now)  # -> AWAITING_AUTHORIZATION
    return track


class TestNominalSequence:
    def test_starts_in_searching(self, machine):
        assert machine.state is MissionState.SEARCHING
        assert machine.target_id is None

    def test_detection_moves_to_detected(self, machine, clock):
        track = make_track(first_seen=clock.now, confirmed=False)
        status = machine.update(track, "UAV-001", now=clock.now)
        assert status.state is MissionState.DETECTED
        assert status.target_id == "UAV-001"

    def test_tentative_track_does_not_reach_tracking(self, machine, clock):
        """An unconfirmed track stays at DETECTED."""
        track = make_track(first_seen=clock.now, confirmed=False)
        machine.update(track, "UAV-001", now=clock.now)
        clock.advance(0.5)
        status = machine.update(track, "UAV-001", now=clock.now)
        assert status.state is MissionState.DETECTED

    def test_confirmed_track_reaches_tracking(self, machine, clock):
        track = make_track(first_seen=clock.now)
        machine.update(track, "UAV-001", now=clock.now)
        status = machine.update(track, "UAV-001", now=clock.now)
        assert status.state is MissionState.TRACKING

    def test_full_sequence_order(self, machine, clock):
        """The mission visits the V0 states in the specified order."""
        seen: list[MissionState] = [machine.state]

        def step(seconds: float, track) -> None:
            clock.advance(seconds)
            state = machine.update(track, "UAV-001", now=clock.now).state
            if state is not seen[-1]:
                seen.append(state)

        track = make_track(first_seen=clock.now)
        for _ in range(2):
            step(0.04, track)
        # The gate opens after confirmation_time + the THREAT_CONFIRMED dwell
        # + follow_time (~4.3 s); allow generous headroom.
        for _ in range(300):
            step(0.04, track)
            if machine.can_authorize:
                break

        assert machine.can_authorize
        machine.request_authorization()
        step(0.04, track)

        for _ in range(200):
            step(0.04, track)
            if machine.state is MissionState.ACTUATED:
                break

        assert seen == [
            MissionState.SEARCHING,
            MissionState.DETECTED,
            MissionState.TRACKING,
            MissionState.THREAT_CONFIRMED,
            MissionState.FOLLOWING,
            MissionState.AWAITING_AUTHORIZATION,
            MissionState.AUTHORIZED,
            MissionState.ACTUATED,
        ]


class TestConfirmationRules:
    def test_low_confidence_track_never_confirms(self, machine, clock):
        """A track below the confidence threshold stays in TRACKING."""
        track = make_track(first_seen=clock.now, confidence=0.30)
        machine.update(track, "UAV-001", now=clock.now)
        machine.update(track, "UAV-001", now=clock.now)
        clock.advance(10.0)
        status = machine.update(track, "UAV-001", now=clock.now)
        assert status.state is MissionState.TRACKING

    def test_wrong_class_never_confirms(self, machine, clock):
        track = make_track(first_seen=clock.now, object_class="car")
        machine.update(track, "UAV-001", now=clock.now)
        machine.update(track, "UAV-001", now=clock.now)
        clock.advance(10.0)
        status = machine.update(track, "UAV-001", now=clock.now)
        assert status.state is MissionState.TRACKING

    def test_dwell_time_is_enforced(self, machine, clock):
        """Confirmation does not happen before confirmation_time elapses."""
        track = make_track(first_seen=clock.now)
        machine.update(track, "UAV-001", now=clock.now)
        machine.update(track, "UAV-001", now=clock.now)

        clock.advance(1.9)  # just under the 2.0s threshold
        assert machine.update(track, "UAV-001", now=clock.now).state is MissionState.TRACKING

        clock.advance(0.2)  # now over it
        assert (
            machine.update(track, "UAV-001", now=clock.now).state
            is MissionState.THREAT_CONFIRMED
        )


class TestAuthorizationInterlock:
    """The safety-critical behaviour: no actuation without operator consent."""

    @pytest.mark.parametrize(
        "state_setup",
        ["searching", "detected", "tracking", "confirmed", "following"],
    )
    def test_authorize_rejected_before_gate(self, machine, clock, state_setup):
        track = make_track(first_seen=clock.now)

        if state_setup != "searching":
            machine.update(track, "UAV-001", now=clock.now)
        if state_setup in ("tracking", "confirmed", "following"):
            machine.update(track, "UAV-001", now=clock.now)
        if state_setup in ("confirmed", "following"):
            clock.advance(2.1)
            machine.update(track, "UAV-001", now=clock.now)
        if state_setup == "following":
            clock.advance(0.9)
            machine.update(track, "UAV-001", now=clock.now)

        assert machine.state is not MissionState.AWAITING_AUTHORIZATION
        assert machine.can_authorize is False

        ok, detail = machine.request_authorization()
        assert ok is False
        assert "rejected" in detail.lower()

        # And it must not have queued the authorization for later.
        clock.advance(5.0)
        for _ in range(50):
            clock.advance(0.05)
            machine.update(track, "UAV-001", now=clock.now)
            if machine.state is MissionState.AUTHORIZED:
                pytest.fail("mission authorized without an accepted operator command")

    def test_cannot_actuate_without_authorization(self, machine, clock):
        """Left alone at the gate, the mission never actuates by itself."""
        track = drive_to_awaiting_authorization(machine, clock)
        assert machine.state is MissionState.AWAITING_AUTHORIZATION

        for _ in range(200):
            clock.advance(0.05)
            machine.update(track, "UAV-001", now=clock.now)
            assert machine.state is MissionState.AWAITING_AUTHORIZATION
            assert machine.should_dispatch_actuation() is False

    def test_authorize_accepted_at_gate(self, machine, clock):
        track = drive_to_awaiting_authorization(machine, clock)
        ok, _ = machine.request_authorization()
        assert ok is True

        clock.advance(0.05)
        status = machine.update(track, "UAV-001", now=clock.now)
        assert status.state is MissionState.AUTHORIZED

    def test_actuation_dispatched_exactly_once(self, machine, clock):
        track = drive_to_awaiting_authorization(machine, clock)
        machine.request_authorization()
        clock.advance(0.05)
        machine.update(track, "UAV-001", now=clock.now)

        assert machine.should_dispatch_actuation() is True
        # Every subsequent call must be False, however many frames run.
        for _ in range(50):
            clock.advance(0.05)
            machine.update(track, "UAV-001", now=clock.now)
            assert machine.should_dispatch_actuation() is False

    def test_authorization_survives_immediate_target_loss(self, machine, clock):
        """Regression: an accepted authorization must not be discarded.

        Observed in a live demo - the operator pressed AUTHORIZE just as the
        target left the frame. The authorization was accepted, then the very
        next update saw no target, went to TARGET_LOST, and silently dropped
        the pending authorization. The gate was open when the operator acted,
        so the decision stands.
        """
        drive_to_awaiting_authorization(machine, clock)
        ok, _ = machine.request_authorization()
        assert ok is True

        # The target vanishes before the next frame is processed.
        clock.advance(2.0)
        status = machine.update(None, None, now=clock.now)

        assert status.state is MissionState.AUTHORIZED
        assert machine.should_dispatch_actuation() is True

    def test_can_authorize_flag_matches_state(self, machine, clock):
        assert machine.can_authorize is False
        drive_to_awaiting_authorization(machine, clock)
        assert machine.can_authorize is True
        assert machine.status().authorization_required is True


class TestTargetLoss:
    def test_brief_dropout_does_not_lose_track(self, machine, clock):
        """A dropout shorter than the grace period holds the current state."""
        track = make_track(first_seen=clock.now)
        machine.update(track, "UAV-001", now=clock.now)
        machine.update(track, "UAV-001", now=clock.now)
        assert machine.state is MissionState.TRACKING

        clock.advance(0.5)  # under the 1.0s grace period
        status = machine.update(None, None, now=clock.now)
        assert status.state is MissionState.TRACKING

    def test_sustained_loss_reaches_target_lost(self, machine, clock):
        track = make_track(first_seen=clock.now)
        machine.update(track, "UAV-001", now=clock.now)
        machine.update(track, "UAV-001", now=clock.now)

        clock.advance(1.5)  # beyond the grace period
        status = machine.update(None, None, now=clock.now)
        assert status.state is MissionState.TARGET_LOST

    def test_target_lost_returns_to_searching(self, machine, clock):
        track = make_track(first_seen=clock.now)
        machine.update(track, "UAV-001", now=clock.now)
        machine.update(track, "UAV-001", now=clock.now)
        clock.advance(1.5)
        machine.update(None, None, now=clock.now)
        assert machine.state is MissionState.TARGET_LOST

        clock.advance(3.0)  # beyond target_lost_hold
        status = machine.update(None, None, now=clock.now)
        assert status.state is MissionState.SEARCHING
        assert status.target_id is None

    def test_reacquisition_from_target_lost(self, machine, clock):
        """A recovered target re-enters the chain rather than stalling."""
        track = make_track(first_seen=clock.now)
        machine.update(track, "UAV-001", now=clock.now)
        machine.update(track, "UAV-001", now=clock.now)
        clock.advance(1.5)
        machine.update(None, None, now=clock.now)
        assert machine.state is MissionState.TARGET_LOST

        clock.advance(0.1)
        status = machine.update(track, "UAV-001", now=clock.now)
        assert status.state is MissionState.DETECTED

    def test_loss_after_authorization_does_not_cancel(self, machine, clock):
        """The operator's decision stands; the sequence completes."""
        track = drive_to_awaiting_authorization(machine, clock)
        machine.request_authorization()
        clock.advance(0.05)
        machine.update(track, "UAV-001", now=clock.now)
        assert machine.state is MissionState.AUTHORIZED

        # Target vanishes mid-engagement.
        for _ in range(60):
            clock.advance(0.05)
            machine.update(None, None, now=clock.now)

        assert machine.state is MissionState.ACTUATED


class TestReset:
    def test_reset_returns_to_searching(self, machine, clock):
        drive_to_awaiting_authorization(machine, clock)
        machine.reset()
        assert machine.state is MissionState.SEARCHING
        assert machine.target_id is None
        assert machine.can_authorize is False

    def test_reset_clears_pending_authorization(self, machine, clock):
        """A reset must discard an authorization that has not yet applied."""
        track = drive_to_awaiting_authorization(machine, clock)
        machine.request_authorization()
        machine.reset()

        for _ in range(50):
            clock.advance(0.05)
            machine.update(track, "UAV-001", now=clock.now)
            if machine.state is MissionState.AUTHORIZED:
                pytest.fail("stale authorization survived a reset")

    def test_auto_reset_after_actuation(self, machine, clock):
        track = drive_to_awaiting_authorization(machine, clock)
        machine.request_authorization()
        clock.advance(0.05)
        machine.update(track, "UAV-001", now=clock.now)

        for _ in range(200):
            clock.advance(0.05)
            machine.update(None, None, now=clock.now)
            if machine.state is MissionState.SEARCHING:
                break

        assert machine.state is MissionState.SEARCHING

    def test_sequence_repeatable_after_reset(self, machine, clock):
        """The full sequence can be run again after a reset."""
        drive_to_awaiting_authorization(machine, clock)
        machine.request_authorization()
        machine.reset()

        clock.advance(0.1)
        drive_to_awaiting_authorization(machine, clock)
        assert machine.can_authorize is True
        ok, _ = machine.request_authorization()
        assert ok is True


class TestEngagementLatch:
    def test_engagement_complete_fires_once(self, machine, clock):
        track = drive_to_awaiting_authorization(machine, clock)
        machine.request_authorization()

        fired = 0
        for _ in range(80):
            clock.advance(0.05)
            machine.update(track, "UAV-001", now=clock.now)
            if machine.consume_engagement_complete():
                fired += 1
            if machine.state is MissionState.SEARCHING:
                break

        assert fired == 1
