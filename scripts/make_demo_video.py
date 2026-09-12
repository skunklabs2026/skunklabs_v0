"""Generate the repeatable demo clip.

The V0 reference document prefers recorded footage over a live camera,
because it removes environmental variability while the software path is
being validated. No suitable drone clip shipped with this repository, so this
script synthesises one that is deterministic, offline, and identical on every
machine.

The clip renders a quadrotor silhouette crossing a gradient sky with drifting
cloud texture and mild sensor noise. That is enough structure for the motion
detector to behave exactly as it would on real sky footage - a small, compact,
moving foreground object against a slowly-varying background.

To use your own footage instead, drop an MP4 at assets/videos/ and point
SKUNK_VIDEO_PATH at it. Nothing else changes.

Usage:
    python scripts/make_demo_video.py
    python scripts/make_demo_video.py --output assets/videos/demo_drone.mp4 --seconds 24
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]

WIDTH, HEIGHT = 1280, 720
FPS = 25


def _sky(width: int, height: int) -> np.ndarray:
    """A vertical gradient sky, BGR."""
    top = np.array([168, 132, 92], dtype=np.float32)  # hazier near horizon
    bottom = np.array([206, 178, 140], dtype=np.float32)
    ramp = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None, None]
    gradient = top[None, None, :] * (1 - ramp) + bottom[None, None, :] * ramp
    return np.repeat(gradient, width, axis=1)


def _cloud_layer(width: int, height: int, seed: int = 7) -> np.ndarray:
    """Smooth low-frequency noise, used as drifting cloud brightness."""
    rng = np.random.default_rng(seed)
    # Generate small and upscale: cheap way to get smooth, organic structure.
    small = rng.random((height // 40 + 2, width // 40 + 2), dtype=np.float32)
    clouds = cv2.resize(small, (width * 2, height), interpolation=cv2.INTER_CUBIC)
    clouds = cv2.GaussianBlur(clouds, (0, 0), 18)
    clouds -= clouds.min()
    clouds /= max(clouds.max(), 1e-6)
    return clouds


def _draw_fixed_wing(frame: np.ndarray, cx: float, cy: float, scale: float) -> None:
    """Draw a delta/flying-wing silhouette (Shahed-like planform)."""
    body = (52, 48, 46)
    span = 34 * scale
    chord = 15 * scale

    # Swept wing as a triangle, plus a slim fuselage.
    wing = np.array(
        [
            [cx, cy - chord * 0.55],
            [cx - span, cy + chord * 0.5],
            [cx + span, cy + chord * 0.5],
        ],
        dtype=np.int32,
    )
    cv2.fillConvexPoly(frame, wing, body, cv2.LINE_AA)
    cv2.ellipse(
        frame,
        (int(round(cx)), int(round(cy))),
        (max(2, int(round(5 * scale))), max(3, int(round(chord * 0.9)))),
        0,
        0,
        360,
        body,
        -1,
        cv2.LINE_AA,
    )


def _draw_drone(frame: np.ndarray, cx: float, cy: float, scale: float, spin: float) -> None:
    """Draw a simple quadrotor silhouette centred at (cx, cy)."""
    body = (54, 50, 48)
    arm_len = 26 * scale
    rotor_r = max(2, int(round(9 * scale)))

    centre = (int(round(cx)), int(round(cy)))

    # Four arms at 45/135/225/315 degrees, plus rotor discs.
    for i in range(4):
        angle = math.radians(45 + 90 * i)
        ex = cx + arm_len * math.cos(angle)
        ey = cy + arm_len * math.sin(angle) * 0.62  # slight top-down foreshortening
        cv2.line(
            frame,
            centre,
            (int(round(ex)), int(round(ey))),
            body,
            max(1, int(round(3 * scale))),
            cv2.LINE_AA,
        )
        cv2.circle(frame, (int(round(ex)), int(round(ey))), rotor_r, body, 1, cv2.LINE_AA)
        # Spinning blade, so the object is not perfectly static internally.
        blade = spin + i * 0.7
        bx = ex + rotor_r * math.cos(blade)
        by = ey + rotor_r * math.sin(blade) * 0.62
        cv2.line(
            frame,
            (int(round(ex)), int(round(ey))),
            (int(round(bx)), int(round(by))),
            body,
            1,
            cv2.LINE_AA,
        )

    # Fuselage.
    cv2.ellipse(
        frame,
        centre,
        (max(2, int(round(13 * scale))), max(2, int(round(8 * scale)))),
        0,
        0,
        360,
        body,
        -1,
        cv2.LINE_AA,
    )


def generate(
    output: Path,
    seconds: float = 24.0,
    seed: int = 7,
    platform: str = "multirotor",
) -> Path:
    """Render a demo clip.

    `platform` selects the flight profile, which is what the backend's
    classifier is meant to tell apart:

      multirotor  a quadrotor weaving across the frame - variable speed,
                  pronounced heading changes, brief near-hovers.
      fixed_wing  a flying wing on a straight, fast, constant-speed run.
    """
    output.parent.mkdir(parents=True, exist_ok=True)

    total_frames = int(seconds * FPS)
    sky = _sky(WIDTH, HEIGHT)
    clouds = _cloud_layer(WIDTH, HEIGHT, seed)
    rng = np.random.default_rng(seed)

    writer = cv2.VideoWriter(
        str(output),
        cv2.VideoWriter_fourcc(*"mp4v"),
        FPS,
        (WIDTH, HEIGHT),
    )
    if not writer.isOpened():
        raise RuntimeError(f"Could not open video writer for {output}")

    # The drone is absent for the opening seconds so the demo genuinely starts
    # in SEARCHING and the background model has clean frames to settle on.
    entry_frame = int(3.0 * FPS)

    for i in range(total_frames):
        # Slow cloud drift keeps the background non-static, which exercises
        # the background subtractor the way real footage would.
        offset = int((i * 0.45) % WIDTH)
        cloud_slice = clouds[:, offset : offset + WIDTH][:, :, None]
        frame = sky + cloud_slice * 26.0 - 10.0

        # Mild sensor noise, so the detector is not working on a clean plate.
        frame += rng.normal(0.0, 2.0, (HEIGHT, WIDTH, 1)).astype(np.float32)
        frame = np.clip(frame, 0, 255).astype(np.uint8)

        if i >= entry_frame:
            t = (i - entry_frame) / max(1, (total_frames - entry_frame))

            if platform == "fixed_wing":
                # A committed straight run at constant speed: no hovering, no
                # sharp turns. This is the profile the classifier should read
                # as FIXED_WING.
                cx = -80 + t * (WIDTH + 160)
                cy = HEIGHT * 0.30 + t * HEIGHT * 0.10
                scale = 0.5 + t * 0.7
                _draw_fixed_wing(frame, cx, cy, scale)
            else:
                # Weaving flight with speed changes and a near-hover midway -
                # the MULTIROTOR profile.
                # Several full direction reversals plus an early hover, so
                # the multirotor signature is present within the first few
                # seconds rather than only late in the clip.
                weave = math.sin(t * math.pi * 7.0)
                dwell = math.exp(-((t - 0.28) ** 2) / 0.002)  # brief hover
                cx = -60 + (t + 0.16 * weave) * (WIDTH + 120) * (1.0 - 0.35 * dwell)
                cy = HEIGHT * 0.34 + weave * HEIGHT * 0.22
                scale = 0.55 + t * 0.95
                _draw_drone(frame, cx, cy, scale, spin=i * 0.9)

        writer.write(frame)

    writer.release()
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the SkunkLabs V0 demo clip.")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "assets" / "videos" / "demo_drone.mp4",
    )
    parser.add_argument("--seconds", type=float, default=24.0)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--platform",
        choices=("multirotor", "fixed_wing"),
        default="multirotor",
        help="Flight profile to render.",
    )
    args = parser.parse_args()

    path = generate(args.output, args.seconds, args.seed, args.platform)
    size_mb = path.stat().st_size / 1e6
    print(f"Wrote {path} ({size_mb:.1f} MB, {args.seconds:.0f}s @ {FPS} fps)")


if __name__ == "__main__":
    main()
