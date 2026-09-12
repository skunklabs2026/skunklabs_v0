import { describe, expect, it } from "vitest";
import { destination, sector, shortestDelta, toLocalKm } from "./geo";

const NODE = { latitude: 49.993, longitude: 36.23 };

describe("display geometry", () => {
  it("round-trips a destination through local kilometres", () => {
    const [latitude, longitude] = destination(NODE, 72, 32);
    const { x, y } = toLocalKm(NODE, { latitude, longitude });
    expect(Math.hypot(x, y)).toBeCloseTo(32, 6);
    expect((Math.atan2(x, y) * 180) / Math.PI).toBeCloseTo(72, 6);
  });

  it("uses the compass convention: north is +y, east is +x", () => {
    const [nLat, nLon] = destination(NODE, 0, 10);
    expect(toLocalKm(NODE, { latitude: nLat, longitude: nLon }).y).toBeCloseTo(
      10,
      6,
    );
    const [eLat, eLon] = destination(NODE, 90, 10);
    expect(toLocalKm(NODE, { latitude: eLat, longitude: eLon }).x).toBeCloseTo(
      10,
      6,
    );
  });

  it("builds a closed wedge starting at the origin", () => {
    const ring = sector(NODE, 72, 5, 9, 12);
    expect(ring).toHaveLength(14);
    expect(ring[0]).toEqual([NODE.latitude, NODE.longitude]);
  });

  it.each([
    [0, 72, 72],
    [350, 10, 20],
    [10, 350, -20],
    [180, 0, 180],
  ])("shortestDelta(%s, %s) = %s", (from, to, expected) => {
    expect(shortestDelta(from, to)).toBe(expected);
  });
});
