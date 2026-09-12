"""Headless end-to-end pipeline check.

Runs the real video source, detector, tracker, rules and state machine over
the configured clip with no server and no UI, and prints the state timeline.
This is the fastest way to tell whether a demo will work before starting
anything else - and the first thing to run if a demo misbehaves.

Usage:
    python scripts/verify_pipeline.py
    python scripts/verify_pipeline.py --authorize-at THREAT_CONFIRMED
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config.settings import get_settings
from backend.mission.rules import build_rule_engine
from backend.mission.state_machine import MissionConfig, MissionStateMachine
from backend.schemas import MissionState
from backend.targets.target_manager import TargetManager
from backend.video.source import build_video_source
from backend.vision.detector import build_detector
from backend.vision.tracker import build_tracker


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-frames", type=int, default=900)
    parser.add_argument(
        "--authorize",
        action="store_true",
        help="Automatically authorize when the gate opens, to exercise the full path.",
    )
    args = parser.parse_args()

    settings = get_settings()
    # Run flat out; we are not pacing for a human viewer here.
    settings = settings.model_copy(update={"target_fps": 0.0, "loop_video": False})

    video = build_video_source(settings)
    detector = build_detector(settings)
    tracker = build_tracker(settings)
    targets = TargetManager()
    mission = MissionStateMachine(
        build_rule_engine(settings),
        MissionConfig(
            confirmation_time=settings.confirmation_time,
            follow_time=settings.follow_time,
            target_lost_grace=settings.target_lost_grace,
            target_lost_hold=settings.target_lost_hold,
            actuated_hold=settings.actuated_hold,
            actuator_duration=settings.actuator_duration,
        ),
    )

    if not video.open():
        print(f"FAIL: could not open video source {video.describe}")
        return 1

    print(f"source   : {video.describe}")
    print(f"detector : {detector.name}")
    print("-" * 68)

    # The clip is paced by wall-clock rules (dwell times), but we read frames
    # as fast as possible. Use a synthetic clock advancing at the nominal
    # frame rate so dwell thresholds behave as they would in real playback.
    frame_period = 1.0 / 25.0
    virtual_now = time.time()

    seen_states: list[tuple[int, MissionState]] = []
    last_state = None
    detections_total = 0
    frames = 0
    actuated = False

    while frames < args.max_frames:
        frame = video.read()
        if frame is None:
            break
        frames += 1
        virtual_now += frame_period

        height, width = frame.shape[:2]
        detections = detector.detect(frame)
        detections_total += len(detections)
        tracks = tracker.update(detections, virtual_now)

        primary = targets.select_primary(tracks)
        designation = (
            targets.designation_for(primary.track_id, primary.object_class) if primary else None
        )
        engaged_track_id = primary.track_id if primary else None
        status = mission.update(primary, designation, now=virtual_now)

        if mission.consume_engagement_complete() and engaged_track_id is not None:
            targets.mark_engaged(engaged_track_id)

        if mission.should_dispatch_actuation():
            actuated = True
            print(f"  [{frames:4d}] SAFE ACTUATION dispatched for {status.target_id}")

        if status.state is not last_state:
            seen_states.append((frames, status.state))
            print(
                f"  [{frames:4d}] {status.state.value:<24} "
                f"target={status.target_id or '-':<8} {status.detail}"
            )
            last_state = status.state

        if args.authorize and mission.can_authorize:
            ok, detail = mission.request_authorization()
            print(f"  [{frames:4d}] operator authorize -> ok={ok}")

    video.release()

    print("-" * 68)
    print(f"frames processed : {frames}")
    print(f"detections total : {detections_total}")
    print(f"states observed  : {' -> '.join(s.value for _, s in seen_states)}")

    reached = {s for _, s in seen_states}
    required = {
        MissionState.SEARCHING,
        MissionState.DETECTED,
        MissionState.TRACKING,
        MissionState.THREAT_CONFIRMED,
        MissionState.FOLLOWING,
        MissionState.AWAITING_AUTHORIZATION,
    }
    missing = required - reached
    if missing:
        print(f"FAIL: never reached {sorted(m.value for m in missing)}")
        return 1
    if args.authorize and not actuated:
        print("FAIL: authorized but no actuation dispatched")
        return 1

    print("PASS: full V0 sequence reached")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
