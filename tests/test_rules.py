"""Demo rule engine tests."""

from __future__ import annotations

from backend.config.settings import Settings
from backend.mission.rules import (
    ClassRule,
    ConfidenceRule,
    DwellRule,
    RuleEngine,
    build_rule_engine,
)
from tests.conftest import make_track


class TestClassRule:
    def test_accepts_configured_class(self):
        rule = ClassRule(("uav",))
        assert rule.evaluate(make_track(object_class="uav"), 1_000.0).passed

    def test_rejects_other_class(self):
        rule = ClassRule(("uav",))
        assert not rule.evaluate(make_track(object_class="bird"), 1_000.0).passed

    def test_is_case_insensitive(self):
        rule = ClassRule(("UAV",))
        assert rule.evaluate(make_track(object_class="uav"), 1_000.0).passed


class TestConfidenceRule:
    def test_passes_at_threshold(self):
        rule = ConfidenceRule(0.60)
        assert rule.evaluate(make_track(confidence=0.60), 1_000.0).passed

    def test_fails_below_threshold(self):
        rule = ConfidenceRule(0.60)
        result = rule.evaluate(make_track(confidence=0.45), 1_000.0)
        assert not result.passed
        assert 0.0 < result.progress < 1.0

    def test_uses_mean_not_instantaneous_confidence(self):
        """One bad frame must not drop a well-established track below threshold."""
        track = make_track(confidence=0.9)
        for value in (0.9, 0.9, 0.9, 0.9):
            track._confidence_history.append(value)
        track._confidence_history.append(0.1)  # a single noisy frame
        track.confidence = 0.1

        assert ConfidenceRule(0.60).evaluate(track, 1_000.0).passed


class TestDwellRule:
    def test_fails_before_duration(self):
        rule = DwellRule(2.0)
        track = make_track(first_seen=1_000.0)
        result = rule.evaluate(track, 1_001.0)
        assert not result.passed
        assert result.progress == 0.5

    def test_passes_after_duration(self):
        rule = DwellRule(2.0)
        track = make_track(first_seen=1_000.0)
        assert rule.evaluate(track, 1_002.5).passed

    def test_progress_is_clamped(self):
        rule = DwellRule(2.0)
        track = make_track(first_seen=1_000.0)
        assert rule.evaluate(track, 1_099.0).progress == 1.0


class TestRuleEngine:
    def test_requires_all_rules(self):
        engine = RuleEngine([ClassRule(("uav",)), ConfidenceRule(0.6), DwellRule(2.0)])
        # Right class and confidence, but not held long enough.
        track = make_track(first_seen=1_000.0, confidence=0.9, object_class="uav")
        assert not engine.evaluate(track, 1_000.5).confirmed
        assert engine.evaluate(track, 1_003.0).confirmed

    def test_progress_is_the_limiting_rule(self):
        engine = RuleEngine([ClassRule(("uav",)), DwellRule(4.0)])
        track = make_track(first_seen=1_000.0)
        outcome = engine.evaluate(track, 1_001.0)
        # Class rule is at 1.0; dwell is at 0.25. The minimum wins.
        assert outcome.progress == 0.25

    def test_summary_names_the_blocking_rule(self):
        engine = RuleEngine([ClassRule(("uav",)), DwellRule(4.0)])
        track = make_track(first_seen=1_000.0)
        assert "tracked=" in engine.evaluate(track, 1_001.0).summary

    def test_rules_are_deterministic(self):
        """The same inputs must always produce the same outcome."""
        engine = build_rule_engine(Settings())
        track = make_track(first_seen=1_000.0)
        outcomes = [engine.evaluate(track, 1_003.0) for _ in range(20)]
        assert len({(o.confirmed, o.progress) for o in outcomes}) == 1

    def test_engine_is_extensible(self):
        """Adding a rule tightens confirmation without touching other code."""

        class AlwaysFailRule(ClassRule):
            name = "never"

            def evaluate(self, track, now):
                from backend.mission.rules import RuleResult

                return RuleResult(name=self.name, passed=False, detail="blocked", progress=0.0)

        base = build_rule_engine(Settings())
        track = make_track(first_seen=1_000.0)
        assert base.evaluate(track, 1_005.0).confirmed

        extended = RuleEngine([*base.rules, AlwaysFailRule()])
        assert not extended.evaluate(track, 1_005.0).confirmed
