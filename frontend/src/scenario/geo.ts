/**
 * Display geometry, mirroring backend/scenario/geo.py.
 *
 * Flat-earth about the launcher. Over the ~40 km the demo shows, the error is
 * a few metres. Used to draw - never to decide anything.
 */

const METERS_PER_DEG_LAT = 111_320;

export interface LatLon {
  latitude: number;
  longitude: number;
}

/** Signed smallest rotation from one heading to another, in (-180, 180]. */
export function shortestDelta(fromDeg: number, toDeg: number): number {
  const delta = ((((toDeg - fromDeg + 180) % 360) + 360) % 360) - 180;
  return delta === -180 ? 180 : delta;
}

/** Point `distanceKm` from `origin` along compass `bearingDeg`, as [lat, lon]. */
export function destination(
  origin: LatLon,
  bearingDeg: number,
  distanceKm: number,
): [number, number] {
  const rad = (bearingDeg * Math.PI) / 180;
  const meters = distanceKm * 1000;
  const metersPerDegLon =
    METERS_PER_DEG_LAT * Math.cos((origin.latitude * Math.PI) / 180);
  return [
    origin.latitude + (Math.cos(rad) * meters) / METERS_PER_DEG_LAT,
    origin.longitude + (Math.sin(rad) * meters) / metersPerDegLon,
  ];
}

/** Kilometres east (`x`) and north (`y`) of `origin`. */
export function toLocalKm(origin: LatLon, point: LatLon): { x: number; y: number } {
  const metersPerDegLon =
    METERS_PER_DEG_LAT * Math.cos((origin.latitude * Math.PI) / 180);
  return {
    x: ((point.longitude - origin.longitude) * metersPerDegLon) / 1000,
    y: ((point.latitude - origin.latitude) * METERS_PER_DEG_LAT) / 1000,
  };
}

/** Distance between two points, kilometres. */
export function distanceKm(a: LatLon, b: LatLon): number {
  const { x, y } = toLocalKm(a, b);
  return Math.hypot(x, y);
}

/** A wedge from `origin` along `bearingDeg`, ±`halfWidthDeg`, as a lat/lon ring. */
export function sector(
  origin: LatLon,
  bearingDeg: number,
  halfWidthDeg: number,
  radiusKm: number,
  segments = 12,
): [number, number][] {
  const ring: [number, number][] = [[origin.latitude, origin.longitude]];
  for (let i = 0; i <= segments; i += 1) {
    const bearing = bearingDeg - halfWidthDeg + (2 * halfWidthDeg * i) / segments;
    ring.push(destination(origin, bearing, radiusKm));
  }
  return ring;
}
