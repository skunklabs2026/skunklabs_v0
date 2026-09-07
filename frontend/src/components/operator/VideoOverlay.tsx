import type {
  InterceptorState,
  InterceptSolution,
  MissionState,
  Target,
} from "../../types";

/**
 * Draws target overlays on top of the video feed.
 *
 * Rendered as SVG in a 0..1 viewBox with `preserveAspectRatio="none"`, so it
 * stretches to exactly the element the video occupies without any pixel maths
 * or resize observers. Backend coordinates are already normalised, so the
 * overlay stays aligned at any window size.
 *
 * Stroke widths are given in a separate constant scaled to the viewBox, since
 * a 0..1 coordinate space makes a "1px" stroke enormous.
 */

const STROKE = 0.0022;

interface Props {
  targets: Target[];
  state: MissionState;
}

interface EngagementProps {
  intercept: InterceptSolution | null;
  interceptor: InterceptorState | null;
  state: MissionState;
}

/** Colour follows mission state — the same language as the banner. */
function targetColor(target: Target, state: MissionState): string {
  if (!target.is_primary) return "var(--idle)";
  switch (state) {
    case "THREAT_CONFIRMED":
    case "FOLLOWING":
    case "AWAITING_AUTHORIZATION":
      return "var(--threat)";
    case "AUTHORIZED":
    case "ACTUATED":
      return "var(--armed)";
    case "TARGET_LOST":
      return "var(--idle)";
    default:
      return "var(--track)";
  }
}

export function VideoOverlay({ targets, state }: Props) {
  return (
    <svg
      className="overlay"
      viewBox="0 0 1 1"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      {targets.map((target, index) => {
        const { x, y, width, height } = target.bbox;
        const color = targetColor(target, state);
        const primary = target.is_primary;
        // Corner brackets rather than a full rectangle: it reads as a
        // targeting reticle and keeps the object itself unobscured.
        const armX = Math.min(width * 0.28, 0.035);
        const armY = Math.min(height * 0.28, 0.035);

        return (
          <g key={`${target.target_id}-${index}`}>
            {/* trajectory tail — makes continuous tracking visible */}
            {primary && target.trail.length > 1 && (
              <polyline
                points={target.trail.map((p) => `${p.x},${p.y}`).join(" ")}
                fill="none"
                stroke={color}
                strokeWidth={STROKE * 0.8}
                strokeOpacity={0.45}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            )}

            <rect
              x={x}
              y={y}
              width={width}
              height={height}
              fill="none"
              stroke={color}
              strokeWidth={STROKE}
              strokeOpacity={primary ? 0.35 : 0.25}
            />

            {/* corner brackets */}
            {primary &&
              (
                [
                  [x, y, armX, armY],
                  [x + width, y, -armX, armY],
                  [x, y + height, armX, -armY],
                  [x + width, y + height, -armX, -armY],
                ] as const
              ).map(([cx, cy, ax, ay], corner) => (
                <path
                  key={corner}
                  d={`M ${cx + ax} ${cy} L ${cx} ${cy} L ${cx} ${cy + ay}`}
                  fill="none"
                  stroke={color}
                  strokeWidth={STROKE * 1.8}
                  strokeLinecap="square"
                />
              ))}

            {/* centre cross on the primary target */}
            {primary && (
              <>
                <line
                  x1={x + width / 2 - armX * 0.35}
                  y1={y + height / 2}
                  x2={x + width / 2 + armX * 0.35}
                  y2={y + height / 2}
                  stroke={color}
                  strokeWidth={STROKE}
                  strokeOpacity={0.8}
                />
                <line
                  x1={x + width / 2}
                  y1={y + height / 2 - armY * 0.35}
                  x2={x + width / 2}
                  y2={y + height / 2 + armY * 0.35}
                  stroke={color}
                  strokeWidth={STROKE}
                  strokeOpacity={0.8}
                />
              </>
            )}

            {/* predicted path — dashed, so it is never mistaken for the
                observed trail. Opacity tracks prediction confidence. */}
            {primary && target.trajectory?.valid && (
              <polyline
                points={[
                  `${x + width / 2},${y + height / 2}`,
                  ...target.trajectory.points.map((p) => `${p.x},${p.y}`),
                ].join(" ")}
                fill="none"
                stroke={color}
                strokeWidth={STROKE * 0.9}
                strokeDasharray={`${STROKE * 4} ${STROKE * 4}`}
                strokeOpacity={0.25 + 0.55 * target.trajectory.confidence}
                strokeLinecap="round"
              />
            )}
          </g>
        );
      })}
    </svg>
  );
}

/**
 * The engagement layer: predicted intercept point and the simulated
 * interceptor in flight.
 *
 * Kept separate from the target layer so it draws on top, and so the
 * distinction stays clear in code — targets are *observed*, this layer is
 * *predicted and simulated*.
 */
export function EngagementOverlay({
  intercept,
  interceptor,
  state,
}: EngagementProps) {
  const armed =
    state === "AWAITING_AUTHORIZATION" ||
    state === "FOLLOWING" ||
    state === "THREAT_CONFIRMED";
  const flying = Boolean(interceptor?.active);

  // The aim point is what the interceptor actually committed to; before
  // launch, show the live estimate instead.
  const marker =
    flying && interceptor?.aim_point
      ? interceptor.aim_point
      : intercept?.feasible
        ? intercept.point
        : null;

  if (!marker && !flying) return null;

  return (
    <svg
      className="overlay"
      viewBox="0 0 1 1"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      {/* predicted intercept point */}
      {marker && (armed || flying) && (
        <g>
          <circle
            cx={marker.x}
            cy={marker.y}
            r={0.018}
            fill="none"
            stroke="var(--armed)"
            strokeWidth={STROKE * 1.2}
            strokeOpacity={0.9}
          />
          <circle
            cx={marker.x}
            cy={marker.y}
            r={0.006}
            fill="var(--armed)"
            fillOpacity={0.85}
          />
        </g>
      )}

      {/* interceptor flight path and vehicle */}
      {flying && interceptor && (
        <g>
          {interceptor.launch_point && interceptor.aim_point && (
            <line
              x1={interceptor.launch_point.x}
              y1={interceptor.launch_point.y}
              x2={interceptor.aim_point.x}
              y2={interceptor.aim_point.y}
              stroke="var(--armed)"
              strokeWidth={STROKE * 0.7}
              strokeOpacity={0.22}
              strokeDasharray={`${STROKE * 3} ${STROKE * 5}`}
            />
          )}

          {interceptor.trail.length > 1 && (
            <polyline
              points={interceptor.trail.map((p) => `${p.x},${p.y}`).join(" ")}
              fill="none"
              stroke="var(--armed)"
              strokeWidth={STROKE * 1.6}
              strokeOpacity={0.75}
              strokeLinecap="round"
            />
          )}

          {interceptor.position && (
            <circle
              cx={interceptor.position.x}
              cy={interceptor.position.y}
              r={interceptor.phase === "INTERCEPT" ? 0.03 : 0.009}
              fill="var(--armed)"
              fillOpacity={interceptor.phase === "INTERCEPT" ? 0.35 : 1}
              stroke="var(--armed)"
              strokeWidth={STROKE}
            />
          )}
        </g>
      )}
    </svg>
  );
}

/**
 * Target labels, as an HTML layer rather than SVG text.
 *
 * The overlay's 0..1 viewBox uses `preserveAspectRatio="none"`, which scales
 * non-uniformly — fine for boxes and lines, but it would distort glyphs. So
 * labels live in their own layer positioned with percentages, where text
 * renders at a true, constant pixel size at any window dimension.
 */
export function TargetLabels({ targets, state }: Props) {
  return (
    <div className="overlay">
      {targets.map((target, index) => {
        const color = targetColor(target, state);
        return (
          <div
            key={`${target.target_id}-${index}`}
            style={{
              position: "absolute",
              left: `${target.bbox.x * 100}%`,
              top: `${target.bbox.y * 100}%`,
              transform: "translateY(-1.35em)",
              fontFamily: "var(--font-label)",
              fontSize: "11px",
              fontWeight: 600,
              letterSpacing: "0.12em",
              color,
              textTransform: "uppercase",
              whiteSpace: "nowrap",
              textShadow: "0 1px 4px rgba(0,0,0,0.95)",
              opacity: target.is_primary ? 1 : 0.55,
            }}
          >
            {target.target_id} · {target.class} ·{" "}
            {Math.round(target.confidence * 100)}%
          </div>
        );
      })}
    </div>
  );
}
