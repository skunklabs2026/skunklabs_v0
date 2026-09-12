import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import {
  BufferGeometry,
  Line,
  LineDashedMaterial,
  MathUtils,
  Shape,
  Vector3,
  type Group,
} from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { useScenarioStore } from "../../scenario/hooks";
import { findNode } from "../../scenario/select";
import { smoothPose, type Pose } from "./articulation";
import { createCompassTexture } from "./compassTexture";
import { LauncherModel, type ModelStatus } from "./LauncherModel";
import { POSE_SMOOTHING_S } from "./modelConfig";
import { PIVOT_HEIGHT } from "./PlaceholderLauncher";

const BACKGROUND = "#060a10";
const COMPASS_RADIUS = 3.2;

function triangle(tipForward: boolean, width: number, length: number): Shape {
  // Shape +Y becomes world −Z (outward at north) once laid flat.
  const shape = new Shape();
  const tip = tipForward ? length / 2 : -length / 2;
  shape.moveTo(0, tip);
  shape.lineTo(width / 2, -tip);
  shape.lineTo(-width / 2, -tip);
  shape.closePath();
  return shape;
}

function Ground() {
  const compass = useMemo(() => createCompassTexture(), []);
  useEffect(() => () => compass.dispose(), [compass]);

  return (
    <group>
      <mesh rotation-x={-Math.PI / 2} receiveShadow>
        <circleGeometry args={[16, 64]} />
        <meshStandardMaterial color="#0a1017" roughness={0.95} metalness={0} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position-y={0.003}>
        <planeGeometry args={[COMPASS_RADIUS * 2, COMPASS_RADIUS * 2]} />
        <meshBasicMaterial map={compass} transparent depthWrite={false} />
      </mesh>
    </group>
  );
}

/**
 * Where the node points (green arrow on the compass ring) and where it has
 * been asked to point (amber tick, plus a dashed ray at the requested yaw and
 * pitch). Updated per frame from the store.
 */
function OrientationMarkers({ nodeId }: { nodeId: string | null }) {
  const store = useScenarioStore();
  const shownNode = useRef(nodeId);
  shownNode.current = nodeId;

  const current = useRef<Group>(null);
  const requested = useRef<Group>(null);
  const requestedRay = useRef<Group>(null);
  const pose = useRef<Pose | null>(null);
  const posedNode = useRef<string | null>(null);

  const arrow = useMemo(() => triangle(true, 0.2, 0.3), []);
  const tick = useMemo(() => triangle(false, 0.18, 0.22), []);
  const ray = useMemo(() => {
    const geometry = new BufferGeometry().setFromPoints([
      new Vector3(0, 0, -1.7),
      new Vector3(0, 0, -9),
    ]);
    const line = new Line(
      geometry,
      new LineDashedMaterial({
        color: "#e9b44c",
        dashSize: 0.18,
        gapSize: 0.14,
        transparent: true,
        opacity: 0.85,
      }),
    );
    line.computeLineDistances();
    return line;
  }, []);
  useEffect(
    () => () => {
      ray.geometry.dispose();
      (ray.material as LineDashedMaterial).dispose();
    },
    [ray],
  );

  useFrame((_, delta) => {
    const snapshot = store.getState().snapshot;
    const id = shownNode.current;
    const node = snapshot && id ? findNode(snapshot, id) : null;
    if (!node || !current.current || !requested.current || !requestedRay.current)
      return;

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
    current.current.rotation.y = -MathUtils.degToRad(pose.current.yawDeg);

    const active = node.state !== "STANDBY";
    requested.current.visible = active;
    requestedRay.current.visible = active;
    requested.current.rotation.y = -MathUtils.degToRad(node.target_yaw_deg);
    requestedRay.current.rotation.set(
      MathUtils.degToRad(node.target_pitch_deg),
      -MathUtils.degToRad(node.target_yaw_deg),
      0,
      "YXZ",
    );
  });

  return (
    <>
      <group ref={current}>
        <mesh
          position={[0, 0.006, -(COMPASS_RADIUS - 0.62)]}
          rotation-x={-Math.PI / 2}
        >
          <shapeGeometry args={[arrow]} />
          <meshBasicMaterial color="#37d483" />
        </mesh>
      </group>
      <group ref={requested} visible={false}>
        <mesh
          position={[0, 0.007, -(COMPASS_RADIUS - 0.02)]}
          rotation-x={-Math.PI / 2}
        >
          <shapeGeometry args={[tick]} />
          <meshBasicMaterial color="#e9b44c" />
        </mesh>
      </group>
      <group ref={requestedRay} position-y={PIVOT_HEIGHT} visible={false}>
        <primitive object={ray} />
      </group>
    </>
  );
}

function CameraRig() {
  const { camera, gl } = useThree();
  const controls = useRef<OrbitControls | null>(null);

  useEffect(() => {
    const orbit = new OrbitControls(camera, gl.domElement);
    orbit.target.set(0, 1.35, 0);
    orbit.enableDamping = true;
    orbit.enablePan = false;
    orbit.minDistance = 5;
    orbit.maxDistance = 18;
    orbit.maxPolarAngle = MathUtils.degToRad(84);
    orbit.update();
    controls.current = orbit;
    return () => {
      orbit.dispose();
      controls.current = null;
    };
  }, [camera, gl]);

  useFrame(() => controls.current?.update());
  return null;
}

/** One node's launcher on its compass pad. Orbit with the mouse. */
export function LauncherScene({
  nodeId,
  onModelStatus,
}: {
  nodeId: string | null;
  onModelStatus?: (status: ModelStatus) => void;
}) {
  return (
    <Canvas
      className="c-canvas"
      // PCF shadows: three r185 deprecates the soft variant R3F picks by default.
      shadows="percentage"
      dpr={[1, 2]}
      camera={{ position: [7.4, 3.6, 7.8], fov: 30, near: 0.1, far: 120 }}
    >
      <color attach="background" args={[BACKGROUND]} />
      <fog attach="fog" args={[BACKGROUND, 16, 38]} />
      <hemisphereLight args={["#c9dcff", "#080c11", 0.7]} />
      <directionalLight
        position={[5, 9, 4]}
        intensity={2.2}
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
        shadow-camera-left={-5}
        shadow-camera-right={5}
        shadow-camera-top={5}
        shadow-camera-bottom={-5}
        shadow-bias={-0.0004}
      />
      <directionalLight position={[-6, 4, -5]} intensity={0.55} color="#7fb0ff" />
      <Ground />
      <OrientationMarkers nodeId={nodeId} />
      <LauncherModel nodeId={nodeId} onStatus={onModelStatus} />
      <CameraRig />
    </Canvas>
  );
}
