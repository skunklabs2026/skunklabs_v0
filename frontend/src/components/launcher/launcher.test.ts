import { renderHook, waitFor } from "@testing-library/react";
import { Group, MathUtils, Quaternion, Vector3 } from "three";
import { afterEach, describe, expect, it, vi } from "vitest";
import { applyPose, findArticulation, smoothPose } from "./articulation";
import { LAUNCHER_MODEL, type LauncherModelConfig } from "./modelConfig";
import {
  loadModelSource,
  looksLikeGltf,
  useLauncherModelSource,
} from "./modelSource";

/** ROOT > BASE, YAW_STAGE > PITCH_STAGE > LAUNCHER - the CAD contract. */
function contractModel() {
  const root = new Group();
  const base = new Group();
  base.name = "BASE";
  const yaw = new Group();
  yaw.name = "YAW_STAGE";
  const pitch = new Group();
  pitch.name = "PITCH_STAGE";
  const launcher = new Group();
  launcher.name = "LAUNCHER";
  pitch.add(launcher);
  yaw.add(pitch);
  root.add(base, yaw);
  return { root, yaw, pitch, launcher };
}

/** Where the canister pack points, in world space. */
function boresight(node: Group): Vector3 {
  node.updateWorldMatrix(true, false);
  return new Vector3(0, 0, -1).applyQuaternion(
    node.getWorldQuaternion(new Quaternion()),
  );
}

describe("articulation", () => {
  it("finds the yaw and pitch stages by name", () => {
    const { root, yaw, pitch } = contractModel();
    const found = findArticulation(root, LAUNCHER_MODEL);
    expect(found.ok).toBe(true);
    if (found.ok) {
      expect(found.articulation.yawStage).toBe(yaw);
      expect(found.articulation.pitchStage).toBe(pitch);
    }
  });

  it("names every missing node", () => {
    expect(findArticulation(new Group(), LAUNCHER_MODEL)).toEqual({
      ok: false,
      missing: ["YAW_STAGE", "PITCH_STAGE"],
    });
  });

  it.each([
    [0, 0, [0, 0, -1]], // north, level
    [90, 0, [1, 0, 0]], // east
    [180, 0, [0, 0, 1]], // south
    [0, 30, [0, 0.5, -Math.sqrt(3) / 2]], // north, pitched up
  ])(
    "yaw %s°, pitch %s° points the pack along %j",
    (yawDeg, pitchDeg, expected) => {
      const { root, launcher } = contractModel();
      const found = findArticulation(root, LAUNCHER_MODEL);
      if (!found.ok) throw new Error("contract model incomplete");
      applyPose(found.articulation, { yawDeg, pitchDeg }, LAUNCHER_MODEL);
      const direction = boresight(launcher);
      expect(direction.x).toBeCloseTo(expected[0], 6);
      expect(direction.y).toBeCloseTo(expected[1], 6);
      expect(direction.z).toBeCloseTo(expected[2], 6);
    },
  );

  it("adds to the CAD rest rotation and honours axis, sign and offset", () => {
    const { root, yaw, pitch } = contractModel();
    yaw.rotation.z = 0.25;
    const config: LauncherModelConfig = {
      ...LAUNCHER_MODEL,
      yaw: { axis: "z", sign: 1, offsetDeg: 90 },
      pitch: { axis: "y", sign: -1, offsetDeg: 0 },
    };
    const found = findArticulation(root, config);
    if (!found.ok) throw new Error("contract model incomplete");
    applyPose(found.articulation, { yawDeg: 10, pitchDeg: 20 }, config);
    expect(yaw.rotation.z).toBeCloseTo(0.25 + MathUtils.degToRad(100), 9);
    expect(pitch.rotation.y).toBeCloseTo(-MathUtils.degToRad(20), 9);
  });
});

describe("smoothPose", () => {
  it("starts at the target", () => {
    expect(smoothPose(null, { yawDeg: 72, pitchDeg: 12 }, 0.016, 0.06)).toEqual({
      yawDeg: 72,
      pitchDeg: 12,
    });
  });

  it("does not move without elapsed time", () => {
    const current = { yawDeg: 10, pitchDeg: 1 };
    expect(smoothPose(current, { yawDeg: 70, pitchDeg: 9 }, 0, 0.06)).toEqual(
      current,
    );
  });

  it("goes the short way through north and stays wrapped", () => {
    const next = smoothPose(
      { yawDeg: 350, pitchDeg: 0 },
      { yawDeg: 10, pitchDeg: 0 },
      0.06,
      0.06,
    );
    // ~63% of the 20° gap, forward through 0°.
    expect(next.yawDeg).toBeCloseTo((350 + 20 * (1 - Math.exp(-1))) % 360, 6);
    expect(next.yawDeg).toBeGreaterThanOrEqual(0);
    expect(next.yawDeg).toBeLessThan(360);
  });
});

describe("model source", () => {
  const bytes = (text: string) =>
    new TextEncoder().encode(text).buffer as ArrayBuffer;
  const glb = () => {
    const buffer = new ArrayBuffer(12);
    new DataView(buffer).setUint32(0, 0x46546c67, true);
    return buffer;
  };

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("recognises glTF and rejects an HTML fallback page", () => {
    expect(looksLikeGltf(glb())).toBe(true);
    expect(looksLikeGltf(bytes('  {"asset":{"version":"2.0"}}'))).toBe(true);
    expect(looksLikeGltf(bytes("<!doctype html><html>"))).toBe(false);
    expect(looksLikeGltf(new ArrayBuffer(0))).toBe(false);
  });

  const respond = (ok: boolean, body: ArrayBuffer) => async () => ({
    ok,
    arrayBuffer: async () => body,
  });

  it("falls back to the placeholder when there is no model", async () => {
    const parse = vi.fn();
    const url = "/models/skunk-launcher.glb";
    for (const fetcher of [
      respond(false, new ArrayBuffer(0)),
      respond(true, bytes("<!doctype html>")),
      async () => {
        throw new TypeError("offline");
      },
    ]) {
      await expect(loadModelSource(url, fetcher, parse)).resolves.toEqual({
        kind: "placeholder",
        reason: `No CAD model at ${url}`,
      });
    }
    expect(parse).not.toHaveBeenCalled();
  });

  it("parses a present model once, relative to its folder", async () => {
    const scene = new Group();
    const parse = vi.fn(async () => ({ scene }));
    const body = glb();
    const source = await loadModelSource(
      "/models/skunk-launcher.glb",
      respond(true, body),
      parse,
    );
    expect(source).toEqual({ kind: "cad", scene });
    expect(parse).toHaveBeenCalledWith(body, "/models/");
  });

  it("reports a model that fails to parse", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const parse = vi.fn(async () => {
      throw new Error("bad");
    });
    const source = await loadModelSource("/m/x.glb", respond(true, glb()), parse);
    expect(source).toMatchObject({
      kind: "placeholder",
      reason: expect.stringMatching(/failed/),
    });
  });

  it("resolves through the hook", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        arrayBuffer: async () => new ArrayBuffer(0),
      })),
    );
    const { result } = renderHook(() =>
      useLauncherModelSource("/models/hook-test.glb"),
    );
    expect(result.current.kind).toBe("loading");
    await waitFor(() => expect(result.current.kind).toBe("placeholder"));
  });
});
