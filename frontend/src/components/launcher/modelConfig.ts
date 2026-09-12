/**
 * How a 3D launcher model plugs into the scenario.
 *
 * The UI never touches model geometry. It sets two angles on two named nodes:
 *
 *   ROOT
 *     BASE              static
 *     YAW_STAGE         rotates about the vertical axis   ← current_yaw_deg
 *       PITCH_STAGE     rotates about its horizontal axis ← current_pitch_deg
 *         LAUNCHER      canister pack, rides the pitch stage
 *
 * The built-in placeholder is assembled with exactly these node names, so the
 * placeholder and a CAD export go through the same code path.
 *
 * >>> TO USE A CAD MODEL <<<
 * 1. Export GLB (or glTF) with the hierarchy above; node names must match
 *    `nodes` below (rename here rather than in CAD if easier).
 * 2. Put it at frontend/public/models/skunk-launcher.glb.
 * 3. Reload. If the file is absent or lacks the nodes, the placeholder is
 *    shown and the launcher view says why.
 * 4. Adjust `transform` (units, up-axis) and `yaw` / `pitch` (axis, sign,
 *    zero offset) until neutral - yaw 000°, pitch 0° - points the canisters
 *    north (away from the default camera) and level.
 *
 * Scene convention: Y up, north = −Z, east = +X, metres. Rotation axes are
 * in each node's local frame, so a Z-up CAD export usually needs
 * `rotationDeg: [-90, 0, 0]` and `yaw.axis: "z"`.
 */

export type RotationAxis = "x" | "y" | "z";

export interface AxisMapping {
  axis: RotationAxis;
  /** +1 or −1: flips the direction a positive angle turns the node. */
  sign: 1 | -1;
  /** Added after the sign, for a model whose zero is not north / level. */
  offsetDeg: number;
}

export interface LauncherModelConfig {
  url: string;
  nodes: {
    yawStage: string;
    pitchStage: string;
  };
  yaw: AxisMapping;
  pitch: AxisMapping;
  transform: {
    scale: number;
    position: [number, number, number];
    rotationDeg: [number, number, number];
  };
}

export const LAUNCHER_MODEL: LauncherModelConfig = {
  url: "/models/skunk-launcher.glb",
  nodes: {
    yawStage: "YAW_STAGE",
    pitchStage: "PITCH_STAGE",
  },
  // Compass yaw is clockwise seen from above; Three.js +Y is counter-clockwise.
  yaw: { axis: "y", sign: -1, offsetDeg: 0 },
  // +X rotation lifts a −Z-facing canister pack.
  pitch: { axis: "x", sign: 1, offsetDeg: 0 },
  transform: {
    scale: 1,
    position: [0, 0, 0],
    rotationDeg: [0, 0, 0],
  },
};

/**
 * Seconds for the rendered pose to close ~63% of the gap to the latest
 * snapshot. Only smooths 30 Hz updates into 60 fps motion - the slew itself
 * (rates, acceleration) is set in backend/scenario/config.py.
 */
export const POSE_SMOOTHING_S = 0.06;
