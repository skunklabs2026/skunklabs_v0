import { useEffect, useState } from "react";
import type { TrackStatus } from "../../scenario/contract";
import { formatElevation, formatHeading, formatKm } from "../../scenario/format";
import { useScenario } from "../../scenario/hooks";
import { findEngagement, findNode, findTrack } from "../../scenario/select";
import {
  CAMERA,
  cameraElevation,
  projectToCamera,
  skylineHeightDeg,
  type CameraFrame,
} from "./cameraProjection";

// SVG units: the frame is 100 wide, centred on the boresight; its height
// follows the pane, so nothing is cropped whatever the layout.
const WIDTH = 100;
const HALF_W = WIDTH / 2;
const UNIT = WIDTH / CAMERA.hfovDeg; // SVG units per degree
const DEFAULT_ASPECT = 16 / 9;

const INK = "rgba(228, 236, 244, 0.9)";
const INK_DIM = "rgba(228, 236, 244, 0.45)";
const INK_FAINT = "rgba(228, 236, 244, 0.22)";
const TRACK_COLOR: Record<TrackStatus, string> = {
  INBOUND: "#ff5a52",
  INTERCEPTED: "#37d483",
  REACHED_SITE: "#8190a0",
};

/** Terrain layers, far to near: parallax factor, haze colour, height scale. */
const RIDGES = [
  { parallax: 0.45, fill: "#39525f", scale: 0.55, phase: 0 },
  { parallax: 0.7, fill: "#263a43", scale: 0.85, phase: 2.1 },
  { parallax: 1, fill: "#131c1f", scale: 1.25, phase: 4.7 },
];

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/**
 * Width / height of an element, kept current as the layout changes. Takes the
 * element itself (from a callback ref), so it starts measuring whenever the
 * element mounts, including after the first snapshot arrives.
 */
function useAspect(element: Element | null): number {
  const [aspect, setAspect] = useState(DEFAULT_ASPECT);
  useEffect(() => {
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setAspect(width / height);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);
  return aspect;
}

interface Sighting {
  id: string;
  status: TrackStatus;
  bearingDeg: number;
  elevationDeg: number;
  rangeKm: number;
}

/** A ridge line across the frame, offset by the camera's heading. */
function ridgePoints(
  yaw: number,
  horizon: number,
  span: number,
  layer: (typeof RIDGES)[number],
  halfH: number,
): string {
  const first = Math.floor(yaw - span);
  const last = Math.ceil(yaw + span);
  const points = [`${(first - yaw) * UNIT},${halfH + 10}`];
  for (let az = first; az <= last; az += 1) {
    const height =
      skylineHeightDeg(az * layer.parallax + layer.phase) * layer.scale;
    points.push(
      `${((az - yaw) * UNIT).toFixed(2)},${(horizon - height * UNIT).toFixed(2)}`,
    );
  }
  points.push(`${(last - yaw) * UNIT},${halfH + 10}`);
  return points.join(" ");
}

function TrackMarker({
  sighting,
  frame,
  halfH,
}: {
  sighting: Sighting;
  frame: CameraFrame;
  halfH: number;
}) {
  const point = projectToCamera(sighting.bearingDeg, sighting.elevationDeg, frame);
  const color = TRACK_COLOR[sighting.status];
  const x = point.x * WIDTH;
  const y = point.y * WIDTH;

  if (!point.visible) {
    // Off-frame: a chevron on the edge, pointing where to look.
    const ex = clamp(x, -HALF_W + 5, HALF_W - 5);
    const ey = clamp(y, -halfH + 9, halfH - 6);
    const angle = (Math.atan2(y, x) * 180) / Math.PI;
    return (
      <g transform={`translate(${ex} ${ey})`} data-testid="camera-track-offscreen">
        <path
          d="M2.4 0 -1.8 -2.1 -1.8 2.1Z"
          fill={color}
          transform={`rotate(${angle})`}
        />
        <text
          y={-3.2}
          textAnchor="middle"
          fontSize="2"
          fill={color}
          letterSpacing="0.2"
        >
          {sighting.id}
        </text>
      </g>
    );
  }

  const label =
    sighting.status === "INTERCEPTED"
      ? "SIMULATED INTERCEPT"
      : `${sighting.id} · ${formatKm(sighting.rangeKm)}`;
  return (
    <g transform={`translate(${x} ${y})`} data-testid="camera-track">
      {/* Tracking gate: corner brackets, not a closed box. */}
      <path
        d="M-3.6 -2.2V-3.6H-2.2M2.2 -3.6H3.6V-2.2M3.6 2.2V3.6H2.2M-2.2 3.6H-3.6V2.2"
        fill="none"
        stroke={color}
        strokeWidth={0.4}
      />
      <circle r={0.3} fill={color} />
      <path d={`M3.6 0H6`} stroke={color} strokeWidth={0.25} opacity={0.7} />
      <text x={6.6} y={0.7} fontSize="2.1" fill={color} letterSpacing="0.18">
        {label}
      </text>
    </g>
  );
}

/**
 * The node's electro-optical camera, rendered rather than filmed.
 *
 * It sits on the yaw stage, so it turns with the node, and its elevation
 * follows the threat it is answering. The chrome is what an EO operator
 * expects: heading tape, elevation ladder, tracking gate, field-of-view
 * corners, and a status strip. Sky, haze and layered terrain give the image
 * depth so the turn is legible.
 */
export function SimulatedCameraView({ nodeId }: { nodeId: string | null }) {
  const [svg, setSvg] = useState<SVGSVGElement | null>(null);
  const aspect = useAspect(svg);
  const snapshot = useScenario().snapshot;
  const node = snapshot && nodeId ? findNode(snapshot, nodeId) : null;
  if (!snapshot || !node) return null;

  const engagement = node.engagement_id
    ? findEngagement(snapshot, node.engagement_id)
    : null;
  const track = engagement ? findTrack(snapshot, engagement.track_id) : null;
  const sighting: Sighting | null =
    engagement && track && track.status !== "REACHED_SITE"
      ? {
          id: track.id,
          status: track.status,
          bearingDeg: engagement.bearing_deg,
          elevationDeg: engagement.elevation_deg,
          rangeKm: engagement.range_km,
        }
      : null;

  const frame: CameraFrame = {
    yawDeg: node.current_yaw_deg,
    elevationDeg: cameraElevation(engagement ? engagement.elevation_deg : null),
    aspect,
  };
  const yaw = frame.yawDeg;
  const height = WIDTH / aspect;
  const halfH = height / 2;
  const horizon = frame.elevationDeg * UNIT;
  const span = CAMERA.hfovDeg / 2 + 3;

  const headingTicks: number[] = [];
  for (let az = Math.ceil((yaw - span) / 5) * 5; az <= yaw + span; az += 5) {
    headingTicks.push(az);
  }
  const elevationTicks: number[] = [];
  for (let deg = -10; deg <= 40; deg += 5) elevationTicks.push(deg);

  const pitchY = clamp(
    -(node.current_pitch_deg - frame.elevationDeg) * UNIT,
    -halfH + 9,
    halfH - 5,
  );

  return (
    <svg
      ref={setSvg}
      className="c-camera-svg"
      viewBox={`${-HALF_W} ${-halfH} ${WIDTH} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label={`Simulated camera at ${node.id}, heading ${formatHeading(yaw)}`}
      fontFamily="IBM Plex Mono, monospace"
    >
      <defs>
        <linearGradient id="c-cam-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#0a1422" />
          <stop offset="0.55" stopColor="#22384b" />
          <stop offset="1" stopColor="#5b7183" />
        </linearGradient>
        <linearGradient id="c-cam-ground" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#1a2420" />
          <stop offset="1" stopColor="#070b09" />
        </linearGradient>
        <radialGradient id="c-cam-vignette" cx="0.5" cy="0.5" r="0.72">
          <stop offset="0.55" stopColor="#000" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity="0.55" />
        </radialGradient>
        <filter id="c-cam-grain" x="0" y="0" width="100%" height="100%">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.9"
            numOctaves="2"
            seed="7"
          />
          <feColorMatrix type="saturate" values="0" />
        </filter>
      </defs>

      {/* Sky, horizon haze and layered terrain. */}
      <rect
        x={-HALF_W}
        y={-halfH - 60}
        width={WIDTH}
        height={halfH + 60 + horizon}
        fill="url(#c-cam-sky)"
      />
      <rect
        x={-HALF_W}
        y={horizon - 3}
        width={WIDTH}
        height={6}
        fill="#8fa6b6"
        opacity={0.18}
      />
      <rect
        x={-HALF_W}
        y={horizon}
        width={WIDTH}
        height={halfH + 60}
        fill="url(#c-cam-ground)"
      />
      {RIDGES.map((layer, index) => (
        <polygon
          key={layer.phase}
          points={ridgePoints(yaw, horizon, span, layer, halfH)}
          fill={layer.fill}
          opacity={0.65 + index * 0.15}
        />
      ))}
      <line
        x1={-HALF_W}
        x2={HALF_W}
        y1={horizon}
        y2={horizon}
        stroke={INK_FAINT}
        strokeWidth={0.1}
      />

      {sighting && <TrackMarker sighting={sighting} frame={frame} halfH={halfH} />}

      {/* Field-of-view corners. */}
      {[
        [-1, -1],
        [1, -1],
        [1, 1],
        [-1, 1],
      ].map(([sx, sy]) => (
        <path
          key={`${sx}${sy}`}
          d={`M${sx * (HALF_W - 3)} ${sy * (halfH - 7.5)}V${sy * (halfH - 3)}H${sx * (HALF_W - 7.5)}`}
          fill="none"
          stroke={INK_DIM}
          strokeWidth={0.22}
        />
      ))}

      {/* Reticle: centre cross with a gap, plus range ticks. */}
      <path
        d="M-9 0H-2.2M2.2 0H9M0 -9V-2.2M0 2.2V9"
        stroke={INK}
        strokeWidth={0.22}
        fill="none"
      />
      {[-6, -3, 3, 6].map((offset) => (
        <path
          key={offset}
          d={`M${offset} -0.8V0.8`}
          stroke={INK_DIM}
          strokeWidth={0.18}
        />
      ))}

      {/* Heading tape along the top. */}
      <rect
        x={-HALF_W}
        y={-halfH}
        width={WIDTH}
        height={6.4}
        fill="rgba(4, 8, 13, 0.55)"
      />
      {headingTicks.map((az) => {
        const x = (az - yaw) * UNIT;
        const major = ((az % 10) + 10) % 10 === 0;
        return (
          <g key={az}>
            <line
              x1={x}
              x2={x}
              y1={-halfH + 6.4}
              y2={-halfH + (major ? 4 : 5.2)}
              stroke={INK_DIM}
              strokeWidth={0.18}
            />
            {major && (
              <text
                x={x}
                y={-halfH + 3.1}
                textAnchor="middle"
                fontSize="1.9"
                fill={INK_DIM}
                letterSpacing="0.15"
              >
                {formatHeading(az, 0).replace("°", "")}
              </text>
            )}
          </g>
        );
      })}
      <path d={`M0 ${-halfH + 6.4}l-1.1 -1.5h2.2Z`} fill={INK} />
      <rect
        x={-5.6}
        y={-halfH + 0.5}
        width={11.2}
        height={3.4}
        fill="#04080d"
        stroke={INK_DIM}
        strokeWidth={0.12}
      />
      <text
        x={0}
        y={-halfH + 3.1}
        textAnchor="middle"
        fontSize="2.2"
        fill={INK}
        letterSpacing="0.2"
      >
        {formatHeading(yaw)}
      </text>

      {/* Elevation ladder down the right edge. */}
      {elevationTicks.map((deg) => {
        const y = -(deg - frame.elevationDeg) * UNIT;
        if (y < -halfH + 8 || y > halfH - 4) return null;
        const major = deg % 10 === 0;
        return (
          <g key={deg}>
            <line
              x1={HALF_W - (major ? 6 : 4)}
              x2={HALF_W - 2.6}
              y1={y}
              y2={y}
              stroke={INK_FAINT}
              strokeWidth={0.16}
            />
            {major && (
              <text
                x={HALF_W - 7}
                y={y + 0.7}
                textAnchor="end"
                fontSize="1.7"
                fill={INK_FAINT}
              >
                {deg}
              </text>
            )}
          </g>
        );
      })}
      <g transform={`translate(${HALF_W - 2.4} ${pitchY})`}>
        <path d="M0 0 -1.8 -1.1 -1.8 1.1Z" fill="#37d483" />
        <text x={-2.6} y={0.7} textAnchor="end" fontSize="1.9" fill="#37d483">
          EL {formatElevation(node.current_pitch_deg)}
        </text>
      </g>

      {/* Status strips. */}
      <text
        x={-HALF_W + 2.4}
        y={-halfH + 10.5}
        fontSize="1.9"
        fill={INK_DIM}
        letterSpacing="0.2"
      >
        {node.id} EO
      </text>
      <text
        x={-HALF_W + 2.4}
        y={-halfH + 13.4}
        fontSize="1.7"
        fill={INK_FAINT}
        letterSpacing="0.2"
      >
        FOV {CAMERA.hfovDeg}.0 WIDE
      </text>
      <g transform={`translate(${HALF_W - 2.4} ${-halfH + 10.5})`}>
        <text textAnchor="end" fontSize="1.7" fill={INK_FAINT} letterSpacing="0.2">
          SIM FEED
        </text>
      </g>
      <text
        x={-HALF_W + 2.4}
        y={halfH - 2.4}
        fontSize="1.7"
        fill={INK_FAINT}
        letterSpacing="0.2"
      >
        {sighting ? `TRACKING ${sighting.id}` : "SECTOR SCAN"}
      </text>
      <text
        x={HALF_W - 2.4}
        y={halfH - 2.4}
        textAnchor="end"
        fontSize="1.7"
        fill={INK_FAINT}
        letterSpacing="0.2"
      >
        {sighting ? `RNG ${sighting.rangeKm.toFixed(1)} KM` : "RNG ---"}
      </text>

      {/* Sensor grain and vignette, over everything. */}
      <rect
        x={-HALF_W}
        y={-halfH}
        width={WIDTH}
        height={height}
        filter="url(#c-cam-grain)"
        opacity={0.06}
        style={{ mixBlendMode: "overlay" }}
      />
      <rect
        x={-HALF_W}
        y={-halfH}
        width={WIDTH}
        height={height}
        fill="url(#c-cam-vignette)"
      />
    </svg>
  );
}
