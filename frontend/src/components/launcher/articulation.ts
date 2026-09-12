/**
 * Drives a launcher model's yaw and pitch nodes. Plain Three.js, no React, so
 * the model contract can be tested without WebGL.
 */

import { MathUtils, type Object3D } from "three";
import type { LauncherModelConfig } from "./modelConfig";

export interface Pose {
  yawDeg: number;
  pitchDeg: number;
}

export interface Articulation {
  yawStage: Object3D;
  pitchStage: Object3D;
  /** The node's own rotation on the driven axis, as authored in CAD. */
  yawRest: number;
  pitchRest: number;
}

export type ArticulationResult =
  { ok: true; articulation: Articulation } | { ok: false; missing: string[] };

export function findArticulation(
  root: Object3D,
  config: LauncherModelConfig,
): ArticulationResult {
  const yawStage = root.getObjectByName(config.nodes.yawStage);
  const pitchStage = root.getObjectByName(config.nodes.pitchStage);
  if (!yawStage || !pitchStage) {
    const missing: string[] = [];
    if (!yawStage) missing.push(config.nodes.yawStage);
    if (!pitchStage) missing.push(config.nodes.pitchStage);
    return { ok: false, missing };
  }
  return {
    ok: true,
    articulation: {
      yawStage,
      pitchStage,
      yawRest: yawStage.rotation[config.yaw.axis],
      pitchRest: pitchStage.rotation[config.pitch.axis],
    },
  };
}

export function applyPose(
  articulation: Articulation,
  pose: Pose,
  config: LauncherModelConfig,
): void {
  const { yaw, pitch } = config;
  articulation.yawStage.rotation[yaw.axis] =
    articulation.yawRest +
    MathUtils.degToRad(yaw.sign * pose.yawDeg + yaw.offsetDeg);
  articulation.pitchStage.rotation[pitch.axis] =
    articulation.pitchRest +
    MathUtils.degToRad(pitch.sign * pose.pitchDeg + pitch.offsetDeg);
}

/**
 * Frame-rate-independent approach from the rendered pose to the latest
 * snapshot. Yaw goes the short way round and stays within [0, 360).
 */
export function smoothPose(
  current: Pose | null,
  target: Pose,
  dtSeconds: number,
  timeConstantS: number,
): Pose {
  if (!current) return { ...target };
  const k = 1 - Math.exp(-Math.max(0, dtSeconds) / timeConstantS);
  const yawDelta =
    ((((target.yawDeg - current.yawDeg + 180) % 360) + 360) % 360) - 180;
  return {
    yawDeg: (((current.yawDeg + yawDelta * k) % 360) + 360) % 360,
    pitchDeg: current.pitchDeg + (target.pitchDeg - current.pitchDeg) * k,
  };
}
