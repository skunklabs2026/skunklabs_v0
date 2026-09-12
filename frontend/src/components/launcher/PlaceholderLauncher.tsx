/**
 * Stand-in launcher until the CAD model exists.
 *
 * Built from primitives, but with the exact node names the CAD contract uses
 * (see modelConfig.ts) - so it is articulated by the same code a real GLB is.
 *
 * Scene convention: Y up, canisters face −Z (north) at yaw 0, pitch 0.
 */

const COLOR = {
  base: "#2a3036",
  stage: "#3a4148",
  pack: "#4d544c",
  dark: "#14181c",
  loaded: "#6b7468",
  spent: "#040506",
  index: "#37d483",
};

const YAW_STAGE_HEIGHT = 0.68;
const PITCH_AXIS_HEIGHT = 1.1;

/** World height of the pitch axis, for scene overlays that start there. */
export const PIVOT_HEIGHT = YAW_STAGE_HEIGHT + PITCH_AXIS_HEIGHT;

/** Six canister mouths, 3 × 2, numbered left to right, top row first. */
const TUBES: [number, number][] = [
  [-0.44, 0.225],
  [0, 0.225],
  [0.44, 0.225],
  [-0.44, -0.225],
  [0, -0.225],
  [0.44, -0.225],
];

function Metal({ color, rough = 0.62 }: { color: string; rough?: number }) {
  return <meshStandardMaterial color={color} metalness={0.45} roughness={rough} />;
}

export function PlaceholderLauncher({ loaded }: { loaded: number }) {
  return (
    <group name="PLACEHOLDER_LAUNCHER">
      <group name="BASE">
        <mesh castShadow receiveShadow position-y={0.08}>
          <cylinderGeometry args={[1.35, 1.42, 0.16, 56]} />
          <Metal color={COLOR.base} />
        </mesh>
        <mesh castShadow receiveShadow position-y={0.41}>
          <cylinderGeometry args={[0.95, 1.08, 0.5, 56]} />
          <Metal color={COLOR.base} />
        </mesh>
        <mesh position-y={0.665}>
          <cylinderGeometry args={[1.0, 1.0, 0.03, 56]} />
          <Metal color={COLOR.dark} />
        </mesh>
      </group>

      <group name="YAW_STAGE" position-y={YAW_STAGE_HEIGHT}>
        <mesh castShadow receiveShadow position-y={0.07}>
          <cylinderGeometry args={[0.95, 0.95, 0.14, 56]} />
          <Metal color={COLOR.stage} />
        </mesh>
        {/* Forward index mark: shows which way the yaw stage faces. */}
        <mesh position={[0, 0.145, -0.86]}>
          <boxGeometry args={[0.16, 0.012, 0.1]} />
          <meshBasicMaterial color={COLOR.index} />
        </mesh>
        <mesh castShadow receiveShadow position={[0, 0.28, 0.12]}>
          <boxGeometry args={[1.0, 0.28, 0.9]} />
          <Metal color={COLOR.stage} />
        </mesh>
        {[-0.86, 0.86].map((x) => (
          <mesh key={x} castShadow receiveShadow position={[x, 0.65, 0]}>
            <boxGeometry args={[0.12, 1.02, 0.42]} />
            <Metal color={COLOR.stage} />
          </mesh>
        ))}

        <group name="PITCH_STAGE" position-y={PITCH_AXIS_HEIGHT}>
          <mesh castShadow rotation-z={Math.PI / 2}>
            <cylinderGeometry args={[0.08, 0.08, 1.9, 24]} />
            <Metal color={COLOR.dark} rough={0.4} />
          </mesh>

          <group name="LAUNCHER" position={[0, 0.02, -0.55]}>
            <mesh castShadow receiveShadow>
              <boxGeometry args={[1.42, 0.94, 2.3]} />
              <Metal color={COLOR.pack} rough={0.75} />
            </mesh>
            {[-0.85, 0, 0.85].map((z) => (
              <mesh key={z} castShadow position-z={z}>
                <boxGeometry args={[1.47, 0.99, 0.07]} />
                <Metal color={COLOR.stage} />
              </mesh>
            ))}
            {TUBES.map(([x, y], index) => (
              <mesh
                key={`${x},${y}`}
                position={[x, y, -1.152]}
                rotation-x={Math.PI / 2}
              >
                <cylinderGeometry args={[0.19, 0.19, 0.012, 32]} />
                <meshStandardMaterial
                  color={index < loaded ? COLOR.loaded : COLOR.spent}
                  metalness={0.3}
                  roughness={index < loaded ? 0.55 : 1}
                />
              </mesh>
            ))}
          </group>
        </group>
      </group>
    </group>
  );
}
