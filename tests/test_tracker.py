"""Tracker and target-manager tests.

The behaviour that matters for the demo is ID persistence: the operator must
be able to trust that "UAV-001" is the same object from frame to frame.
"""

from __future__ import annotations

from backend.targets.target_manager import TargetManager
from backend.vision.tracker import ByteTracker, iou
from tests.conftest import make_detection


class TestIoU:
    def test_identical_boxes(self):
        assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0

    def test_disjoint_boxes(self):
        assert iou((0, 0, 10, 10), (50, 50, 60, 60)) == 0.0

    def test_partial_overlap(self):
        # 5x10 intersection, union 150 => 50/150
        assert iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest_approx(50 / 150)


def pytest_approx(value, tol=1e-6):
    class _Approx:
        def __eq__(self, other):
            return abs(other - value) < tol

        def __repr__(self):
            return f"~{value}"

    return _Approx()


class TestByteTracker:
    def test_creates_track_from_detection(self):
        tracker = ByteTracker(min_hits=1)
        tracks = tracker.update([make_detection()], 1_000.0)
        assert len(tracks) == 1
        assert tracks[0].confirmed

    def test_min_hits_gates_confirmation(self):
        tracker = ByteTracker(min_hits=3)
        tracks = tracker.update([make_detection()], 1_000.0)
        assert not tracks[0].confirmed

        for i in range(1, 3):
            tracks = tracker.update([make_detection()], 1_000.0 + i * 0.04)
        assert tracks[0].confirmed

    def test_id_persists_across_frames(self):
        """A steadily moving object keeps one ID."""
        tracker = ByteTracker(min_hits=2)
        ids = set()
        for i in range(30):
            detection = make_detection(x=100.0 + i * 4, y=100.0)
            tracks = tracker.update([detection], 1_000.0 + i * 0.04)
            ids.update(t.track_id for t in tracks)
        assert ids == {1}

    def test_low_confidence_detection_preserves_id(self):
        """The ByteTrack second stage recovers a fading detection."""
        tracker = ByteTracker(min_hits=2, high_confidence=0.6)
        for i in range(5):
            tracker.update(
                [make_detection(x=100.0 + i * 3, confidence=0.9)], 1_000.0 + i * 0.04
            )

        # Confidence collapses but the object is still there.
        tracks = tracker.update([make_detection(x=115.0, confidence=0.35)], 1_000.3)
        assert len(tracks) == 1
        assert tracks[0].track_id == 1

    def test_low_confidence_alone_does_not_spawn_a_track(self):
        """Noise must not create tracks."""
        tracker = ByteTracker(min_hits=1, high_confidence=0.6)
        assert tracker.update([make_detection(confidence=0.2)], 1_000.0) == []

    def test_track_survives_brief_dropout(self):
        tracker = ByteTracker(min_hits=2, max_age=30)
        for i in range(5):
            tracker.update([make_detection(x=100.0 + i * 2)], 1_000.0 + i * 0.04)

        for i in range(10):  # ten frames with nothing
            tracks = tracker.update([], 1_000.2 + i * 0.04)
        assert len(tracks) == 1
        assert tracks[0].track_id == 1

    def test_track_expires_after_max_age(self):
        tracker = ByteTracker(min_hits=2, max_age=5)
        tracker.update([make_detection()], 1_000.0)
        tracker.update([make_detection()], 1_000.04)

        for i in range(10):
            tracks = tracker.update([], 1_000.1 + i * 0.04)
        assert tracks == []

    def test_separate_objects_get_separate_ids(self):
        tracker = ByteTracker(min_hits=1)
        tracks = tracker.update(
            [make_detection(x=50.0, y=50.0), make_detection(x=500.0, y=400.0)],
            1_000.0,
        )
        assert len({t.track_id for t in tracks}) == 2

    def test_fast_target_keeps_its_id_when_boxes_do_not_overlap(self):
        """The reason stage 3 exists.

        A small target crossing quickly moves further than its own width
        between frames, so consecutive boxes have IoU exactly 0. With IoU
        association alone the track breaks and a new ID is issued every
        frame — visibly wrong on the one target that matters.
        """
        tracker = ByteTracker(min_hits=2, gate_scale=4.0)
        ids = set()
        # 20 px wide, moving 60 px per frame: no overlap at all.
        for i in range(20):
            detection = make_detection(x=50.0 + i * 60.0, y=200.0, width=20.0, height=20.0)
            tracks = tracker.update([detection], 1_000.0 + i * 0.04)
            ids.update(t.track_id for t in tracks)

        assert ids == {1}, f"track identity broke on a fast target: {ids}"
        assert len(tracks) == 1

    def test_without_the_gate_a_fast_target_fragments(self):
        """Confirms the gate is what fixes it, not something else."""
        tracker = ByteTracker(min_hits=2, gate_scale=0.0)
        ids = set()
        for i in range(20):
            detection = make_detection(x=50.0 + i * 60.0, y=200.0, width=20.0, height=20.0)
            tracker.update([detection], 1_000.0 + i * 0.04)
            ids.update(t.track_id for t in tracker.tracks)
        assert len(ids) > 1

    def test_gate_rejects_a_wildly_different_size(self):
        """A nearby object of very different size must not steal the track."""
        tracker = ByteTracker(min_hits=1, gate_scale=4.0)
        tracker.update([make_detection(x=100.0, y=100.0, width=20.0, height=20.0)], 1_000.0)

        # Same area, but 8x the size — not the same object.
        tracks = tracker.update(
            [make_detection(x=130.0, y=100.0, width=160.0, height=160.0)], 1_000.04
        )
        assert len(tracks) == 2

    def test_gate_does_not_capture_distant_detections(self):
        tracker = ByteTracker(min_hits=1, gate_scale=4.0)
        tracker.update([make_detection(x=100.0, y=100.0, width=20.0, height=20.0)], 1_000.0)
        tracks = tracker.update(
            [make_detection(x=900.0, y=700.0, width=20.0, height=20.0)], 1_000.04
        )
        assert len(tracks) == 2

    def test_reset_clears_tracks_and_ids(self):
        tracker = ByteTracker(min_hits=1)
        tracker.update([make_detection()], 1_000.0)
        tracker.reset()
        tracks = tracker.update([make_detection()], 1_001.0)
        assert tracks[0].track_id == 1


class TestTargetManager:
    def test_designations_are_stable(self):
        manager = TargetManager()
        assert manager.designation_for(7, "uav") == "UAV-001"
        assert manager.designation_for(7, "uav") == "UAV-001"
        assert manager.designation_for(9, "uav") == "UAV-002"

    def test_designation_follows_detected_class(self):
        """A generic detector must not label a person as a UAV."""
        manager = TargetManager()
        assert manager.designation_for(1, "person") == "PERSON-001"
        assert manager.designation_for(2, "uav") == "UAV-001"
        assert manager.designation_for(3, "person") == "PERSON-002"

    def test_designation_is_frozen_after_assignment(self):
        """A flickering class label must not renumber a live target."""
        manager = TargetManager()
        assert manager.designation_for(1, "uav") == "UAV-001"
        assert manager.designation_for(1, "bird") == "UAV-001"

    def test_designation_handles_awkward_class_names(self):
        manager = TargetManager()
        assert manager.designation_for(1, "traffic light") == "TRAFFIC_LIGHT-001"
        assert manager.designation_for(2, "") == "UAV-001"
        assert manager.designation_for(3, None) == "UAV-002"

    def test_primary_is_sticky(self):
        """The primary target does not switch while its track is alive."""
        manager = TargetManager()
        from tests.conftest import make_track

        first = make_track(track_id=1, hits=5)
        second = make_track(track_id=2, hits=50)

        assert manager.select_primary([first]).track_id == 1
        # A "better" track appears; the primary must not switch.
        assert manager.select_primary([first, second]).track_id == 1

    def test_engaged_track_is_not_reselected(self):
        """After actuation the same track must not immediately re-arm."""
        manager = TargetManager()
        from tests.conftest import make_track

        track = make_track(track_id=1)
        assert manager.select_primary([track]).track_id == 1

        manager.mark_engaged(1)
        assert manager.select_primary([track]) is None

        # A genuinely new track is still eligible.
        new_track = make_track(track_id=2)
        assert manager.select_primary([track, new_track]).track_id == 2

    def test_reset_clears_engaged_and_numbering(self):
        manager = TargetManager()
        from tests.conftest import make_track

        manager.designation_for(1)
        manager.mark_engaged(1)
        manager.reset()

        track = make_track(track_id=1)
        assert manager.select_primary([track]).track_id == 1
        assert manager.designation_for(1) == "UAV-001"

    def test_bboxes_are_normalised_and_clamped(self):
        """Boxes must always land inside 0..1 for the UI overlay."""
        manager = TargetManager()
        from tests.conftest import make_track

        track = make_track(track_id=1)
        # Push the box partly off the left edge, as a prediction can.
        track.x = -30.0
        track.y = -10.0

        targets = manager.to_targets(
            [track], frame_width=960, frame_height=540, now=1_000.0, primary_track_id=1
        )
        box = targets[0].bbox
        assert 0.0 <= box.x <= 1.0
        assert 0.0 <= box.y <= 1.0
        assert box.x + box.width <= 1.0
        assert box.y + box.height <= 1.0

    def test_primary_flag_is_set(self):
        manager = TargetManager()
        from tests.conftest import make_track

        tracks = [make_track(track_id=1), make_track(track_id=2)]
        targets = manager.to_targets(
            tracks, frame_width=960, frame_height=540, now=1_000.0, primary_track_id=2
        )
        assert [t.is_primary for t in targets] == [False, True]
