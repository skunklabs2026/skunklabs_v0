import { formatElevation, formatHeading } from "../../scenario/format";
import { shortestDelta } from "../../scenario/geo";

interface Props {
  kind: "yaw" | "pitch";
  current: number;
  requested: number;
}

const COPY = {
  yaw: { title: "Yaw", subtitle: "Azimuth · 360°", format: formatHeading },
  pitch: { title: "Pitch", subtitle: "Elevation", format: formatElevation },
};

/**
 * A small dial: green needle = where the stage points, amber tick = where it
 * has been asked to point. Yaw is a compass (north up); pitch a quarter arc.
 */
function Dial({ kind, current, requested }: Props) {
  const polar = (deg: number, r: number) => {
    // Yaw: compass angle. Pitch: 0° horizontal right, 90° straight up.
    const rad =
      kind === "yaw" ? ((deg - 90) * Math.PI) / 180 : (-deg * Math.PI) / 180;
    return [Math.cos(rad) * r, Math.sin(rad) * r] as const;
  };
  const [nx, ny] = polar(current, 27);
  const [r1x, r1y] = polar(requested, 26);
  const [r2x, r2y] = polar(requested, 34);
  const origin = kind === "yaw" ? "0 0" : "-30 30";

  return (
    <svg
      className="c-dial"
      viewBox={kind === "yaw" ? "-36 -36 72 72" : "-36 -40 72 72"}
      aria-hidden="true"
    >
      <g
        transform={
          kind === "yaw" ? undefined : `translate(${origin.split(" ")[0]} 30)`
        }
      >
        {kind === "yaw" ? (
          <>
            <circle r="30" fill="none" stroke="#253549" />
            {[0, 90, 180, 270].map((deg) => {
              const [ax, ay] = polar(deg, 30);
              const [bx, by] = polar(deg, 25);
              return (
                <line key={deg} x1={ax} y1={ay} x2={bx} y2={by} stroke="#5f6d7d" />
              );
            })}
            <text y="-18" textAnchor="middle" fontSize="7" fill="#5f6d7d">
              N
            </text>
          </>
        ) : (
          <>
            <path d="M 30 0 A 30 30 0 0 0 0 -30" fill="none" stroke="#253549" />
            <line x1="0" y1="0" x2="34" y2="0" stroke="#253549" />
          </>
        )}
        <line
          x1={r1x}
          y1={r1y}
          x2={r2x}
          y2={r2y}
          stroke="#e9b44c"
          strokeWidth="2.5"
        />
        <line
          x1="0"
          y1="0"
          x2={nx}
          y2={ny}
          stroke="#37d483"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <circle r="2.5" fill="#37d483" />
      </g>
    </svg>
  );
}

export function AxisReadout({ kind, current, requested }: Props) {
  const copy = COPY[kind];
  const error =
    kind === "yaw" ? shortestDelta(current, requested) : requested - current;

  return (
    <section className="c-axis" aria-label={copy.title}>
      <div className="c-axis-head">
        <h2>{copy.title}</h2>
        <span className="c-label">{copy.subtitle}</span>
      </div>
      <div className="c-axis-body">
        <div>
          <span className="c-axis-current" data-testid={`${kind}-current`}>
            {copy.format(current)}
          </span>
          <dl className="c-axis-rows">
            <dt>Requested</dt>
            <dd className="is-requested" data-testid={`${kind}-requested`}>
              {copy.format(requested)}
            </dd>
            <dt>Error</dt>
            <dd>{Math.abs(error).toFixed(1)}°</dd>
          </dl>
        </div>
        <Dial kind={kind} current={current} requested={requested} />
      </div>
    </section>
  );
}
