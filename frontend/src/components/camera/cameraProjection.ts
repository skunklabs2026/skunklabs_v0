/**
 * Geometry for the simulated launcher camera.
 *
 * The camera rides the yaw stage - it turns with the launcher - and its
 * elevation follows the selected track's line of sight, as an EO sensor slaved
 * to that track would. Display geometry only: a linear angle-to-screen
 * mapping, not a lens model.
 */

import { shortestDelta } from "../../scenario/geo";

export const CAMERA = {
  /** Horizontal field of view, degrees. The vertical one follows the pane shape. */
  hfovDeg: 24,
  /** Look-up angle with no track selected, degrees. */
  restElevationDeg: 2,
  maxElevationDeg: 25,
};

/** Where the camera is pointing, and the shape of the frame it fills. */
export interface CameraFrame {
  yawDeg: number;
  elevationDeg: number;
  /** Frame width / height. */
  aspect: number;
}

export interface CameraPoint {
  /** Fractions of frame width from the centre: x right, y down. */
  x: number;
  y: number;
  visible: boolean;
}

/** The camera's elevation: up to the selected track's line of sight, if any. */
export function cameraElevation(trackElevationDeg: number | null): number {
  if (trackElevationDeg === null) return CAMERA.restElevationDeg;
  return Math.min(
    CAMERA.maxElevationDeg,
    Math.max(CAMERA.restElevationDeg, trackElevationDeg),
  );
}

/** Where a direction (compass bearing, elevation) lands in the camera frame. */
export function projectToCamera(
  bearingDeg: number,
  elevationDeg: number,
  frame: CameraFrame,
): CameraPoint {
  const x = shortestDelta(frame.yawDeg, bearingDeg) / CAMERA.hfovDeg;
  const y = -(elevationDeg - frame.elevationDeg) / CAMERA.hfovDeg;
  const halfHeight = 0.5 / frame.aspect;
  return { x, y, visible: Math.abs(x) <= 0.5 && Math.abs(y) <= halfHeight };
}

/**
 * Height of the distant terrain above the horizon at a compass azimuth,
 * degrees. Deterministic, so the skyline scrolls consistently as the launcher
 * turns - the cue that the camera is moving.
 */
export function skylineHeightDeg(azimuthDeg: number): number {
  const r = (azimuthDeg * Math.PI) / 180;
  const h =
    0.35 +
    0.3 * Math.sin(3 * r) +
    0.2 * Math.sin(7 * r + 1.3) +
    0.12 * Math.sin(17 * r + 0.4);
  return Math.max(0.05, h);
}
