"""Target management.

Bridges raw tracks and the operator's view of the world:

  * assigns stable, human-readable designations ("UAV-001") to track IDs
  * selects the single *primary* target the mission acts on
  * converts pixel geometry to the normalised coordinates the UI overlays with

V0 is explicitly a single-relevant-target scenario, so exactly one primary
target exists at a time. All tracks are still reported to the UI, so the
operator can see the whole picture, but only the primary drives the mission.
"""

from __future__ import annotations

from backend.schemas import BBox, Point, Target
from backend.vision.tracker import Track


class TargetManager:
    """Maps tracks to operator-facing targets and picks the primary."""

    def __init__(self, *, designation_prefix: str = "UAV") -> None:
        # Fallback prefix, used when a detector reports no usable class.
        self.designation_prefix = designation_prefix
        self._designations: dict[int, str] = {}
        # One counter per class, so the first person is PERSON-001 even if
        # twenty UAVs were designated first.
        self._counters: dict[str, int] = {}
        self._primary_track_id: int | None = None
        # Tracks that have already been engaged this session. They are never
        # selected as primary again — see mark_engaged().
        self._engaged: set[int] = set()

    def reset(self) -> None:
        """Clear designations. Numbering restarts at 001 for the next run."""
        self._designations.clear()
        self._counters.clear()
        self._primary_track_id = None
        self._engaged.clear()

    def mark_engaged(self, track_id: int) -> None:
        """Retire a track from further engagement.

        Called once actuation completes. Without this the still-live track
        instantly re-satisfies every dwell rule — it has been tracked for
        many seconds by definition — and the mission snaps straight back to
        AWAITING_AUTHORIZATION on a target that was just engaged. Retiring
        the track means the demo re-arms only on a genuinely new acquisition.
        """
        self._engaged.add(track_id)
        if self._primary_track_id == track_id:
            self._primary_track_id = None

    def has_designation(self, track_id: int) -> bool:
        """Whether this track has already been designated.

        Lets the caller emit TRACK_CREATED exactly once per track, without
        `designation_for` having to report whether it minted a new name.
        """
        return track_id in self._designations

    def designation_for(self, track_id: int, object_class: str | None = None) -> str:
        """Stable operator designation for a track ID, e.g. "UAV-001".

        The prefix comes from the detected class, so a generic detector
        running on arbitrary footage reports PERSON-001 and CAR-002 rather
        than labelling everything UAV — which would be actively misleading.

        Assigned once and then frozen: a class label that flickers between
        frames must not renumber a target the operator is watching.
        """
        existing = self._designations.get(track_id)
        if existing is not None:
            return existing

        prefix = self._prefix_for(object_class)
        number = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = number

        designation = f"{prefix}-{number:03d}"
        self._designations[track_id] = designation
        return designation

    def _prefix_for(self, object_class: str | None) -> str:
        if not object_class:
            return self.designation_prefix
        # COCO labels can contain spaces ("traffic light") or hyphens.
        cleaned = "".join(
            c if c.isalnum() else "_" for c in object_class.strip().upper()
        ).strip("_")
        return cleaned or self.designation_prefix

    @property
    def primary_track_id(self) -> int | None:
        return self._primary_track_id

    def select_primary(self, tracks: list[Track]) -> Track | None:
        """Choose the track the mission should act on.

        Sticky by design: once a track is primary it stays primary while it
        lives. Switching targets mid-engagement would be both confusing to
        the operator and wrong for V0's single-target scope.
        """
        eligible = [t for t in tracks if t.track_id not in self._engaged]
        by_id = {t.track_id: t for t in eligible}

        current = by_id.get(self._primary_track_id) if self._primary_track_id else None
        if current is not None and current.confirmed:
            return current

        # Prefer confirmed tracks; among them, the longest-lived one, since
        # that is the target the operator has been watching.
        candidates = [t for t in eligible if t.confirmed]
        if not candidates:
            self._primary_track_id = None
            return None

        primary = max(candidates, key=lambda t: (t.hits, t.mean_confidence))
        self._primary_track_id = primary.track_id
        return primary

    def to_targets(
        self,
        tracks: list[Track],
        *,
        frame_width: int,
        frame_height: int,
        now: float,
        primary_track_id: int | None,
    ) -> list[Target]:
        """Render tracks as API targets in normalised coordinates."""
        if frame_width <= 0 or frame_height <= 0:
            return []

        fw, fh = float(frame_width), float(frame_height)
        targets: list[Target] = []

        for track in tracks:
            # Clamp to the frame: a predicted box can drift off-edge during a
            # dropout, and the UI overlay must stay inside the video element.
            x = min(max(track.x / fw, 0.0), 1.0)
            y = min(max(track.y / fh, 0.0), 1.0)
            width = min(max(track.width / fw, 0.0), 1.0 - x)
            height = min(max(track.height / fh, 0.0), 1.0 - y)

            # Only confirmed tracks consume a designation. A transient noise
            # blip would otherwise burn a number, and the operator would see
            # the primary target labelled UAV-057 a minute into the demo.
            designation = (
                self.designation_for(track.track_id, track.object_class)
                if track.confirmed
                else "UNCONFIRMED"
            )

            targets.append(
                Target(
                    target_id=designation,
                    object_class=track.object_class,
                    confidence=round(track.mean_confidence, 4),
                    bbox=BBox(x=x, y=y, width=width, height=height),
                    tracking=track.confirmed,
                    age_frames=track.total_frames,
                    track_duration=round(track.duration(now), 3),
                    trail=[
                        Point(
                            x=min(max(cx / fw, 0.0), 1.0),
                            y=min(max(cy / fh, 0.0), 1.0),
                        )
                        for cx, cy in track.trail
                    ],
                    is_primary=track.track_id == primary_track_id,
                )
            )

        return targets
