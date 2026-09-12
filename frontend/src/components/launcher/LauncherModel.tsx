import { useFrame } from "@react-three/fiber";
import { useEffect, useRef, useState } from "react";
import { MathUtils, type Group, type Mesh } from "three";
import { useScenarioStore, useScenarioValue } from "../../scenario/hooks";
import { findNode } from "../../scenario/select";
import {
  applyPose,
  findArticulation,
  smoothPose,
  type Articulation,
  type Pose,
} from "./articulation";
import {
  LAUNCHER_MODEL,
  POSE_SMOOTHING_S,
  type LauncherModelConfig,
} from "./modelConfig";
import { useLauncherModelSource } from "./modelSource";
import { PlaceholderLauncher } from "./PlaceholderLauncher";

export interface ModelStatus {
  kind: "loading" | "placeholder" | "cad";
  detail: string;
}

interface Props {
  /** Which node this launcher shows. */
  nodeId: string | null;
  config?: LauncherModelConfig;
  onStatus?: (status: ModelStatus) => void;
}

/**
 * The articulated launcher of one node: the CAD model when one is present,
 * else the placeholder. Either way, each frame it reads that node's yaw and
 * pitch from the store and applies them - no React re-render per frame.
 */
export function LauncherModel({
  nodeId,
  config = LAUNCHER_MODEL,
  onStatus,
}: Props) {
  const store = useScenarioStore();
  const source = useLauncherModelSource(config.url);
  const loaded = useScenarioValue((state) => {
    const snapshot = state.snapshot;
    if (!snapshot || !nodeId) return 0;
    return findNode(snapshot, nodeId)?.inventory ?? 0;
  });
  const [missing, setMissing] = useState<string[] | null>(null);

  const root = useRef<Group>(null);
  const articulation = useRef<Articulation | null>(null);
  const pose = useRef<Pose | null>(null);
  const posedNode = useRef<string | null>(null);
  const shownNode = useRef(nodeId);
  shownNode.current = nodeId;

  const showCad = source.kind === "cad" && missing === null;

  // The model in the tree changed: find its nodes again on the next frame.
  useEffect(() => {
    articulation.current = null;
  }, [showCad]);

  useEffect(() => {
    if (source.kind !== "cad") return;
    source.scene.traverse((object) => {
      if ((object as Mesh).isMesh) object.castShadow = object.receiveShadow = true;
    });
  }, [source]);

  useEffect(() => {
    if (!onStatus) return;
    if (source.kind === "loading") {
      onStatus({ kind: "loading", detail: "Loading launcher model…" });
    } else if (showCad) {
      onStatus({ kind: "cad", detail: `CAD model · ${config.url}` });
    } else if (missing) {
      onStatus({
        kind: "placeholder",
        detail: `CAD model lacks node ${missing.join(", ")} - placeholder shown`,
      });
    } else {
      onStatus({ kind: "placeholder", detail: "Placeholder model" });
    }
  }, [source, showCad, missing, config.url, onStatus]);

  useFrame((_, delta) => {
    const group = root.current;
    const snapshot = store.getState().snapshot;
    const id = shownNode.current;
    const node = snapshot && id ? findNode(snapshot, id) : null;
    if (!group || !node) return;

    if (!articulation.current) {
      const found = findArticulation(group, config);
      if (!found.ok) {
        if (showCad) setMissing(found.missing);
        return;
      }
      articulation.current = found.articulation;
    }

    // Switching nodes shows a different launcher: snap, never sweep between them.
    if (posedNode.current !== node.id) {
      pose.current = null;
      posedNode.current = node.id;
    }
    pose.current = smoothPose(
      pose.current,
      { yawDeg: node.current_yaw_deg, pitchDeg: node.current_pitch_deg },
      delta,
      POSE_SMOOTHING_S,
    );
    applyPose(articulation.current, pose.current, config);
  });

  if (source.kind === "loading") return null;

  const { scale, position, rotationDeg } = config.transform;
  return (
    <group ref={root}>
      {showCad ? (
        <group
          scale={scale}
          position={position}
          rotation={
            rotationDeg.map((deg) => MathUtils.degToRad(deg)) as [
              number,
              number,
              number,
            ]
          }
        >
          <primitive object={source.scene} dispose={null} />
        </group>
      ) : (
        <PlaceholderLauncher loaded={loaded} />
      )}
    </group>
  );
}
