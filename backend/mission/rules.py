"""V0 demo rule engine.

Deterministic, inspectable rules that decide when a track qualifies as a
confirmed target *for demonstration purposes*.

=== IMPORTANT SCOPE NOTE ===
This is demo logic. It is NOT a threat-identification capability and must not
be described as one. It answers a narrow question — "has this track satisfied
the pre-agreed demo criteria?" — using three transparent, configurable checks.
There is no inference, no model, and no LLM in this layer, by design: the V0
reference document requires state transitions to be deterministic and
inspectable.

Rules are modular. Adding a criterion means appending a `Rule` to the engine;
nothing else changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from backend.vision.tracker import Track


@dataclass(frozen=True)
class RuleResult:
    """Outcome of evaluating one rule against one track."""

    name: str
    passed: bool
    detail: str
    # 0..1 progress toward satisfying the rule, for UI progress indicators.
    progress: float = 0.0


class Rule(ABC):
    """One configurable demo criterion."""

    name: str = "rule"

    @abstractmethod
    def evaluate(self, track: Track, now: float) -> RuleResult:
        """Evaluate this rule against a track at time `now`."""


class ClassRule(Rule):
    """The track must be classified as one of the accepted classes."""

    name = "classification"

    def __init__(self, accepted_classes: tuple[str, ...] = ("uav",)) -> None:
        self.accepted = {c.lower() for c in accepted_classes}

    def evaluate(self, track: Track, now: float) -> RuleResult:
        actual = track.object_class.lower()
        passed = actual in self.accepted
        return RuleResult(
            name=self.name,
            passed=passed,
            detail=f"class={actual}",
            progress=1.0 if passed else 0.0,
        )


class ConfidenceRule(Rule):
    """Mean track confidence must exceed a threshold.

    Uses the rolling mean rather than the instantaneous value so a single
    noisy frame cannot trip — or untrip — confirmation.
    """

    name = "confidence"

    def __init__(self, threshold: float = 0.60) -> None:
        self.threshold = threshold

    def evaluate(self, track: Track, now: float) -> RuleResult:
        confidence = track.mean_confidence
        passed = confidence >= self.threshold
        progress = min(1.0, confidence / self.threshold) if self.threshold > 0 else 1.0
        return RuleResult(
            name=self.name,
            passed=passed,
            detail=f"confidence={confidence:.2f} (>= {self.threshold:.2f})",
            progress=progress,
        )


class DwellRule(Rule):
    """The track must have been held continuously for a minimum duration.

    This is the rule that makes confirmation feel deliberate rather than
    instantaneous, and it is the main defence against a transient false
    positive reaching THREAT_CONFIRMED.
    """

    name = "dwell"

    def __init__(self, min_duration: float = 2.0) -> None:
        self.min_duration = min_duration

    def evaluate(self, track: Track, now: float) -> RuleResult:
        held = track.duration(now)
        passed = held >= self.min_duration
        progress = min(1.0, held / self.min_duration) if self.min_duration > 0 else 1.0
        return RuleResult(
            name=self.name,
            passed=passed,
            detail=f"tracked={held:.1f}s (>= {self.min_duration:.1f}s)",
            progress=progress,
        )


@dataclass(frozen=True)
class ConfirmationOutcome:
    """Aggregate result across every rule."""

    confirmed: bool
    results: tuple[RuleResult, ...]
    progress: float  # min progress across rules — the limiting criterion

    @property
    def summary(self) -> str:
        """One line naming the rule currently blocking confirmation.

        The *first* failing rule is reported, so the operator sees one
        actionable reason rather than a list:

        >>> held = RuleResult("dwell", True, "tracked=3.0s (>= 2.0s)", 1.0)
        >>> weak = RuleResult("confidence", False, "confidence=0.41 (>= 0.60)", 0.68)
        >>> ConfirmationOutcome(False, (held, weak), 0.68).summary
        'confidence=0.41 (>= 0.60)'
        >>> ConfirmationOutcome(True, (held,), 1.0).summary
        'all demo criteria satisfied'
        """
        if self.confirmed:
            return "all demo criteria satisfied"
        blocking = [r for r in self.results if not r.passed]
        return blocking[0].detail if blocking else "evaluating"


class RuleEngine:
    """Evaluates all demo rules against a track.

    Confirmation requires *every* rule to pass. Reported progress is the
    minimum across rules, so the UI progress ring reflects the criterion that
    is actually holding things up.

    A track that satisfies two criteria out of three is not confirmed, and
    the reported progress is the laggard's, not the average:

    >>> from backend.vision.tracker import Track
    >>> track = Track(
    ...     track_id=1, x=0.4, y=0.4, width=0.05, height=0.05,
    ...     confidence=0.9, object_class="uav", first_seen=0.0, last_seen=1.0,
    ... )
    >>> engine = RuleEngine([ClassRule(("uav",)), ConfidenceRule(0.6), DwellRule(2.0)])
    >>> outcome = engine.evaluate(track, now=1.0)
    >>> outcome.confirmed, round(outcome.progress, 2)
    (False, 0.5)
    >>> outcome.summary
    'tracked=1.0s (>= 2.0s)'

    One more second of dwell is all that is missing:

    >>> outcome = engine.evaluate(track, now=2.0)
    >>> outcome.confirmed, outcome.summary
    (True, 'all demo criteria satisfied')
    """

    def __init__(self, rules: list[Rule]) -> None:
        self.rules = rules

    def evaluate(self, track: Track, now: float) -> ConfirmationOutcome:
        results = tuple(rule.evaluate(track, now) for rule in self.rules)
        confirmed = all(r.passed for r in results)
        progress = min((r.progress for r in results), default=0.0)
        return ConfirmationOutcome(confirmed=confirmed, results=results, progress=progress)


def build_rule_engine(settings) -> RuleEngine:
    """Assemble the configured V0 rule set."""
    return RuleEngine(
        [
            ClassRule(settings.confirmation_classes),
            ConfidenceRule(settings.confirmation_confidence),
            DwellRule(settings.confirmation_time),
        ]
    )
