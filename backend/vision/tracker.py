"""Multi-object tracking.

`Tracker` turns per-frame detections into persistent tracks with stable IDs.
This is what lets the UI say "we are still following the *same* drone" rather
than redrawing an unrelated box every frame.

`ByteTracker` is a compact implementation of the ByteTrack association
strategy, which the V0 reference document recommends:

  1. Associate high-confidence detections to existing tracks by IoU.
  2. Associate the *low*-confidence leftovers to the still-unmatched tracks.

Step 2 is the part that matters: when a drone becomes partially occluded or
blurs on a fast pan, its detection confidence drops but it does not vanish.
Recovering it from the low-confidence pool preserves the track ID instead of
dropping the track and issuing a new ID — which would visibly break the
"same target" illusion the demo depends on.

Motion is smoothed with a constant-velocity estimate rather than a full
Kalman filter. For a single target on a short clip this is sufficient, and it
keeps the module dependency-free and easy to reason about.
"""

from __future__ import annotations

import itertools
import math
from collections import deque
from dataclasses import dataclass, field

from backend.vision.detector import Detection


def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """Intersection-over-union of two xyxy boxes."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    intersection = iw * ih
    if intersection <= 0.0:
        return 0.0

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


@dataclass
class Track:
    """A persistent target across frames."""

    track_id: int
    x: float
    y: float
    width: float
    height: float
    confidence: float
    object_class: str
    first_seen: float  # unix seconds
    last_seen: float
    hits: int = 1  # total frames matched
    age: int = 0  # frames since last match
    total_frames: int = 1  # frames since the track was created
    confirmed: bool = False
    velocity: tuple[float, float] = (0.0, 0.0)
    trail: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=48))
    # Rolling mean confidence — steadier for rule evaluation than the
    # instantaneous per-frame value, which is noisy.
    _confidence_history: deque[float] = field(default_factory=lambda: deque(maxlen=15))

    @property
    def xyxy(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)

    @property
    def mean_confidence(self) -> float:
        if not self._confidence_history:
            return self.confidence
        return sum(self._confidence_history) / len(self._confidence_history)

    def duration(self, now: float) -> float:
        """Seconds this track has existed."""
        return max(0.0, now - self.first_seen)

    def predict(self) -> None:
        """Advance the box by its last known velocity.

        Called for every track each frame *before* association, so a fast
        target is matched against where it is going, not where it was.
        """
        vx, vy = self.velocity
        self.x += vx
        self.y += vy
        self.age += 1
        self.total_frames += 1

    def update(self, detection: Detection, now: float, *, min_hits: int) -> None:
        """Fold in a matched detection."""
        prev_cx, prev_cy = self.center

        self.x = detection.x
        self.y = detection.y
        self.width = detection.width
        self.height = detection.height
        self.confidence = detection.confidence
        self.object_class = detection.object_class
        self.last_seen = now
        self.hits += 1
        self.age = 0
        self._confidence_history.append(detection.confidence)

        cx, cy = self.center
        # Exponential smoothing keeps the prediction stable against jitter
        # while still reacting to a genuine change of direction.
        alpha = 0.6
        vx, vy = self.velocity
        self.velocity = (
            alpha * (cx - prev_cx) + (1 - alpha) * vx,
            alpha * (cy - prev_cy) + (1 - alpha) * vy,
        )
        self.trail.append((cx, cy))

        if not self.confirmed and self.hits >= min_hits:
            self.confirmed = True


class Tracker:
    """Interface for multi-object trackers."""

    def update(self, detections: list[Detection], now: float) -> list[Track]:
        """Advance the tracker one frame and return the live tracks."""
        raise NotImplementedError

    def reset(self) -> None:
        """Drop all tracks and restart ID numbering."""
        raise NotImplementedError


class ByteTracker(Tracker):
    """ByteTrack-style IoU tracker with two-stage association."""

    def __init__(
        self,
        *,
        iou_threshold: float = 0.20,
        max_age: int = 30,
        min_hits: int = 3,
        trail_length: int = 48,
        high_confidence: float = 0.6,
        gate_scale: float = 4.0,
    ) -> None:
        self.iou_threshold = iou_threshold
        self.max_age = max_age
        self.min_hits = min_hits
        self.trail_length = trail_length
        self.high_confidence = high_confidence
        # Proximity gate, in multiples of target size. 0 disables stage 3.
        self.gate_scale = gate_scale
        self._tracks: list[Track] = []
        self._id_counter = itertools.count(1)

    def reset(self) -> None:
        self._tracks = []
        self._id_counter = itertools.count(1)

    @property
    def tracks(self) -> list[Track]:
        return list(self._tracks)

    def update(self, detections: list[Detection], now: float) -> list[Track]:
        for track in self._tracks:
            track.predict()

        high = [d for d in detections if d.confidence >= self.high_confidence]
        low = [d for d in detections if d.confidence < self.high_confidence]

        # Stage 1: high-confidence detections against all tracks.
        unmatched_tracks = list(self._tracks)
        unmatched_high = self._associate(unmatched_tracks, high, now)

        # Stage 2: low-confidence detections against whatever is still
        # unmatched. This is what preserves IDs through brief dropouts.
        unmatched_low = self._associate(unmatched_tracks, low, now)

        # Stage 3: proximity gate.
        #
        # IoU is useless for a small, fast target: if the object moves further
        # than its own width between frames, consecutive boxes do not overlap
        # at all, IoU is exactly 0, and the track breaks — the operator sees
        # the ID jump every few frames on precisely the target that matters
        # most. Falling back to centre distance, gated by object size and the
        # track's own predicted motion, keeps the identity through fast
        # crossing motion without letting unrelated objects capture a track.
        if self.gate_scale > 0:
            leftovers = unmatched_high + unmatched_low
            still_unmatched = self._associate_by_distance(unmatched_tracks, leftovers, now)
            unmatched_high = [d for d in unmatched_high if d in still_unmatched]

        # Any high-confidence detection that matched nothing starts a track.
        # Low-confidence leftovers deliberately do not — that would let noise
        # spawn tracks.
        for detection in unmatched_high:
            self._spawn(detection, now)

        # Retire tracks that have gone unmatched for too long.
        self._tracks = [t for t in self._tracks if t.age <= self.max_age]
        return self._tracks

    def _associate(
        self,
        unmatched_tracks: list[Track],
        detections: list[Detection],
        now: float,
    ) -> list[Detection]:
        """Greedily match detections to tracks by IoU.

        Mutates `unmatched_tracks` in place, removing matched ones, and
        returns the detections that found no track.

        Greedy highest-IoU-first is used instead of the Hungarian algorithm:
        with a single relevant target the result is identical, and it avoids
        a scipy dependency.
        """
        if not detections or not unmatched_tracks:
            return list(detections)

        pairs: list[tuple[float, int, int]] = []
        for ti, track in enumerate(unmatched_tracks):
            for di, detection in enumerate(detections):
                score = iou(track.xyxy, detection.xyxy)
                if score >= self.iou_threshold:
                    pairs.append((score, ti, di))
        pairs.sort(reverse=True)

        used_tracks: set[int] = set()
        used_dets: set[int] = set()
        for _, ti, di in pairs:
            if ti in used_tracks or di in used_dets:
                continue
            used_tracks.add(ti)
            used_dets.add(di)
            unmatched_tracks[ti].update(detections[di], now, min_hits=self.min_hits)

        for ti in sorted(used_tracks, reverse=True):
            unmatched_tracks.pop(ti)

        return [d for di, d in enumerate(detections) if di not in used_dets]

    def _associate_by_distance(
        self,
        unmatched_tracks: list[Track],
        detections: list[Detection],
        now: float,
    ) -> list[Detection]:
        """Match remaining pairs by centre distance within a size gate.

        The gate scales with the larger of the two objects and with how fast
        the track is already moving, so a genuinely fast target is allowed a
        proportionally larger jump while a slow one stays tightly gated.
        """
        if not detections or not unmatched_tracks:
            return list(detections)

        pairs: list[tuple[float, int, int]] = []
        for ti, track in enumerate(unmatched_tracks):
            tcx, tcy = track.center
            track_size = max(track.width, track.height)
            speed = math.hypot(*track.velocity)

            for di, detection in enumerate(detections):
                dcx, dcy = detection.center
                size = max(track_size, detection.width, detection.height)
                gate = self.gate_scale * size + speed

                distance = math.hypot(dcx - tcx, dcy - tcy)
                if distance > gate:
                    continue

                # Reject wildly mismatched sizes — a distant bird should not
                # capture the track of anearer target that happens to be nearby.
                det_size = max(detection.width, detection.height)
                if track_size > 0 and det_size > 0:
                    ratio = max(track_size, det_size) / min(track_size, det_size)
                    if ratio > 3.0:
                        continue

                # Closer is better; expressed as a score so the same
                # greedy-highest-first loop applies.
                pairs.append((1.0 - distance / gate, ti, di))

        pairs.sort(reverse=True)

        used_tracks: set[int] = set()
        used_dets: set[int] = set()
        for _, ti, di in pairs:
            if ti in used_tracks or di in used_dets:
                continue
            used_tracks.add(ti)
            used_dets.add(di)
            unmatched_tracks[ti].update(detections[di], now, min_hits=self.min_hits)

        for ti in sorted(used_tracks, reverse=True):
            unmatched_tracks.pop(ti)

        return [d for di, d in enumerate(detections) if di not in used_dets]

    def _spawn(self, detection: Detection, now: float) -> Track:
        track = Track(
            track_id=next(self._id_counter),
            x=detection.x,
            y=detection.y,
            width=detection.width,
            height=detection.height,
            confidence=detection.confidence,
            object_class=detection.object_class,
            first_seen=now,
            last_seen=now,
            trail=deque(maxlen=self.trail_length),
        )
        track._confidence_history.append(detection.confidence)
        track.trail.append(track.center)
        # min_hits == 1 means "confirm immediately"; honour that on creation.
        if self.min_hits <= 1:
            track.confirmed = True
        self._tracks.append(track)
        return track


def build_tracker(settings) -> Tracker:
    return ByteTracker(
        iou_threshold=settings.track_iou_threshold,
        max_age=settings.track_max_age,
        min_hits=settings.track_min_hits,
        trail_length=settings.track_trail_length,
        gate_scale=settings.track_gate_scale,
    )
