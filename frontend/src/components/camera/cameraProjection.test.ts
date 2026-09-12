import { describe, expect, it } from "vitest";
import {
  CAMERA,
  cameraElevation,
  projectToCamera,
  skylineHeightDeg,
  type CameraFrame,
} from "./cameraProjection";

const FRAME: CameraFrame = { yawDeg: 72, elevationDeg: 2, aspect: 16 / 9 };

describe("projectToCamera", () => {
  it("puts the boresight at the centre", () => {
    expect(projectToCamera(72, 2, FRAME)).toEqual({ x: 0, y: -0, visible: true });
  });

  it("maps half the horizontal field of view to the frame edge", () => {
    const edge = 72 + CAMERA.hfovDeg / 2;
    expect(projectToCamera(edge, 2, FRAME)).toMatchObject({
      x: 0.5,
      visible: true,
    });
    expect(projectToCamera(edge + 1, 2, FRAME).visible).toBe(false);
  });

  it("takes the short way across north", () => {
    const frame = { ...FRAME, yawDeg: 355 };
    expect(projectToCamera(5, 2, frame).x).toBeCloseTo(10 / CAMERA.hfovDeg, 9);
  });

  it("puts higher elevations above the centre, clipped by the frame's shape", () => {
    expect(projectToCamera(72, 5, FRAME).y).toBeLessThan(0);
    expect(projectToCamera(72, 8, FRAME).visible).toBe(true);
    // The same direction falls outside a wide, short pane.
    expect(projectToCamera(72, 8, { ...FRAME, aspect: 3 }).visible).toBe(false);
  });
});

describe("cameraElevation", () => {
  it("rests just above the horizon, and follows a selected track within limits", () => {
    expect(cameraElevation(null)).toBe(CAMERA.restElevationDeg);
    expect(cameraElevation(6.5)).toBe(6.5);
    expect(cameraElevation(0.4)).toBe(CAMERA.restElevationDeg);
    expect(cameraElevation(80)).toBe(CAMERA.maxElevationDeg);
  });
});

describe("skylineHeightDeg", () => {
  it("is deterministic and never below the horizon", () => {
    for (let azimuth = 0; azimuth < 360; azimuth += 7) {
      const height = skylineHeightDeg(azimuth);
      expect(height).toBeCloseTo(skylineHeightDeg(azimuth + 360), 9);
      expect(height).toBeGreaterThanOrEqual(0.05);
    }
  });
});
