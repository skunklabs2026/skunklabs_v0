import type { MissionState, TacticalPicture, TacticalTrack } from "../../types";
import { STATE_COLOR } from "../../format";

interface Props {
  tactical: TacticalPicture | null;
  state: MissionState;
}

/**
 * The local tactical picture - the canister, its detection sector, the tracks
 * it is holding, and where the primary track is projected to go.
 *
 * >>> WHAT THIS IS NOT <<<
 * There is no map here, and deliberately no attempt to look like one. V0 has
 * no GPS, no compass and no rangefinder, so this is a plan-style rendering of
 * *relative* position within the sensor's own field of view. The frame label
 * is drawn on the view itself so a screenshot cannot be mistaken for a
 * geographic display.
 *
 * >>> DESIGN RULES <<<
 * Only confirmed tracks are plotted - the backend filters them, and unconfirmed
 * candidates are reported as a count in the corner. One label, on the primary.
 * Everything else is a mark. A tactical view whose job is to make one target
 * obvious fails the moment it becomes a field of competing labels.
 */

// Plan-view geometry, in the SVG's own 0..100 coordinate space.
const CANISTER = { x: 50, y: 86 };
const SECTOR_HALF_WIDTH = 40;
const SECTOR_DEPTH = 70;

/**
 * Apparent size at which a track is drawn hard up against the canister.
 *
 * Apparent size is the only proximity cue an uncalibrated camera offers, and
 * a drone typically subtends a few percent of the frame - so a linear mapping
 * pinned every track to the far edge in a single clump. The square root
 * spreads the useful range across the sector. It remains a *relative* cue:
 * there are no units on it and none are implied.
 */
const NEAR_REFERENCE = 0.3;

function nearness(apparentSize: number): number {
  return Math.max(0, Math.min(1, Math.sqrt(apparentSize / NEAR_REFERENCE)));
}

/**
 * Fraction of the way from the canister to the far edge of the sector.
 *
 * The floor keeps a very near track off the canister marker itself.
 */
function reach(depth: number): number {
  return 0.08 + 0.92 * depth;
}

/**
 * Where a bearing/depth pair falls in the plan view.
 *
 * The sector is a triangle, so its half-width at any depth is exactly
 * `SECTOR_HALF_WIDTH * reach(depth)`. Bearing is scaled by that same factor -
 * not an independent curve - so a track at the edge of the field of view is
 * drawn on the edge of the sector rather than just outside it.
 */
function project(bearing: number, depth: number): { x: number; y: number } {
  const extent = reach(depth);
  return {
    x: CANISTER.x + bearing * SECTOR_HALF_WIDTH * extent,
    y: CANISTER.y - SECTOR_DEPTH * extent,
  };
}

function plot(track: TacticalTrack) {
  return project(track.bearing_norm, 1 - nearness(track.apparent_size));
}

/**
 * The projected path, drawn as a dashed lead line from the track.
 *
 * Held at the track's current depth for its whole length: bearing can be
 * extrapolated from observed motion, range cannot, because range was never
 * measured. A path that also swept toward the canister would be inventing a
 * closing rate.
 */
function ProjectedPath({ track, color }: { track: TacticalTrack; color: string }) {
  if (track.path.length < 2) return null;

  const depth = 1 - nearness(track.apparent_size);
  const points = track.path
    .map((point) => {
      const { x, y } = project(point.x, depth);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <polyline
      points={points}
      fill="none"
      stroke={color}
      strokeWidth={0.6}
      strokeDasharray="1.6 1.4"
      strokeLinecap="round"
      opacity={0.65}
      markerEnd="url(#tac-arrow)"
    />
  );
}

function TrackMark({ track, color }: { track: TacticalTrack; color: string }) {
  const { x, y } = plot(track);

  // Secondary tracks are marks, not labelled entries. They are there so the
  // operator can see the whole picture, not to compete for attention with the
  // target the mission is acting on.
  if (!track.is_primary) {
    return (
      <g className="tac-track">
        <circle cx={x} cy={y} r={1.6} className="tac-secondary" />
      </g>
    );
  }

  return (
    <g className="tac-track is-primary" style={{ color }}>
      <ProjectedPath track={track} color={color} />

      {/* Lock brackets rather than a filled blob - it reads as an instrument
          cue and stays legible against the sector fill. */}
      <g stroke={color} strokeWidth={0.6} fill="none">
        <path
          d={`M ${x - 4} ${y - 1.8} L ${x - 4} ${y - 4} L ${x - 1.8} ${y - 4}`}
        />
        <path
          d={`M ${x + 4} ${y - 1.8} L ${x + 4} ${y - 4} L ${x + 1.8} ${y - 4}`}
        />
        <path
          d={`M ${x - 4} ${y + 1.8} L ${x - 4} ${y + 4} L ${x - 1.8} ${y + 4}`}
        />
        <path
          d={`M ${x + 4} ${y + 1.8} L ${x + 4} ${y + 4} L ${x + 1.8} ${y + 4}`}
        />
      </g>
      <circle cx={x} cy={y} r={1.7} fill={color} />

      {/* Leader line to a label placed clear of the mark, so the designation
          never sits on top of the thing it names. */}
      <line
        x1={x}
        y1={y - 5}
        x2={x}
        y2={y - 8.5}
        stroke={color}
        strokeWidth={0.4}
        opacity={0.6}
      />
      <text x={x} y={y - 10} className="tac-label" textAnchor="middle" fill={color}>
        {track.target_id}
      </text>
    </g>
  );
}

export function TacticalView({ tactical, state }: Props) {
  const tracks = tactical?.tracks ?? [];
  const candidates = tactical?.candidates ?? 0;
  const color = STATE_COLOR[state];

  // The primary is drawn last so its brackets and label sit above every other
  // mark, whatever order the backend sent them in.
  const ordered = [...tracks].sort(
    (a, b) => Number(a.is_primary) - Number(b.is_primary),
  );

  const sector = [
    `M ${CANISTER.x} ${CANISTER.y}`,
    `L ${CANISTER.x - SECTOR_HALF_WIDTH} ${CANISTER.y - SECTOR_DEPTH}`,
    `L ${CANISTER.x + SECTOR_HALF_WIDTH} ${CANISTER.y - SECTOR_DEPTH}`,
    "Z",
  ].join(" ");

  return (
    <div className="tactical">
      <svg
        className="tactical-plot"
        viewBox="0 0 100 100"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Local tactical picture, sensor frame, relative coordinates"
      >
        <defs>
          <marker
            id="tac-arrow"
            viewBox="0 0 8 8"
            refX="5"
            refY="4"
            markerWidth="3.5"
            markerHeight="3.5"
            orient="auto"
          >
            <path d="M 0 1 L 7 4 L 0 7 z" fill="currentColor" />
          </marker>
        </defs>

        <path d={sector} className="tac-sector" />

        {/* Unlabelled proximity bands. Without a rangefinder any number
            against these would be invented, so they carry none. */}
        {[0.35, 0.7].map((ring) => {
          const left = project(-1, ring);
          const right = project(1, ring);
          return (
            <line
              key={ring}
              x1={left.x}
              y1={left.y}
              x2={right.x}
              y2={right.y}
              className="tac-ring"
            />
          );
        })}

        <line
          x1={CANISTER.x}
          y1={CANISTER.y}
          x2={CANISTER.x}
          y2={CANISTER.y - SECTOR_DEPTH}
          className="tac-boresight"
        />

        {ordered.map((track) => (
          <TrackMark key={track.target_id} track={track} color={color} />
        ))}

        {/* The canister - the origin of everything on this view. */}
        <circle
          cx={CANISTER.x}
          cy={CANISTER.y}
          r={5}
          className="tac-canister-ring"
        />
        <circle cx={CANISTER.x} cy={CANISTER.y} r={2.4} className="tac-canister" />
        <text
          x={CANISTER.x}
          y={CANISTER.y + 9.5}
          className="tac-label is-canister"
          textAnchor="middle"
        >
          CANISTER 01
        </text>
      </svg>

      <div className="tactical-meta">
        <span>
          {tracks.length === 0 ? "No tracks held" : `${tracks.length} track held`}
        </span>
        {candidates > 0 && (
          <span
            className="tactical-candidates"
            title="Detections the tracker has not yet confirmed. Counted, not plotted."
          >
            {candidates} unconfirmed
          </span>
        )}
      </div>

      <div className="tactical-frame-label">
        {tactical?.frame_label ??
          "LOCAL TRACK · RELATIVE COORDINATES · SENSOR FRAME"}
      </div>
    </div>
  );
}
