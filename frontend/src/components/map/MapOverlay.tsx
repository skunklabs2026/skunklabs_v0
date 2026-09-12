import { useScenario } from "../../scenario/hooks";
import { missionCounts } from "../../scenario/select";
import { toneClass } from "../shell/toneClass";

function Legend() {
  return (
    <div className="c-map-hud c-hud-tl">
      <div className="c-hud-card">
        <h2 className="c-panel-title">Defense picture · north up</h2>
        <ul className="c-legend">
          <li>
            <svg viewBox="0 0 16 12" aria-hidden="true">
              <rect
                x="3"
                y="1"
                width="10"
                height="10"
                fill="rgba(90,169,255,.3)"
                stroke="#5aa9ff"
                strokeWidth="1.4"
              />
            </svg>
            Protected infrastructure
          </li>
          <li>
            <svg viewBox="0 0 16 12" aria-hidden="true">
              <path
                d="M1 6H15"
                stroke="#5aa9ff"
                strokeWidth="2"
                strokeDasharray="4 2"
              />
            </svg>
            Protected radius
          </li>
          <li>
            <svg viewBox="0 0 16 12" aria-hidden="true">
              <circle
                cx="8"
                cy="6"
                r="4.5"
                fill="#37d483"
                stroke="#06140c"
                strokeWidth="1.2"
              />
            </svg>
            Defense node · heading
          </li>
          <li>
            <svg viewBox="0 0 16 12" aria-hidden="true">
              <circle
                cx="8"
                cy="6"
                r="5"
                fill="rgba(55,212,131,.15)"
                stroke="rgba(55,212,131,.6)"
              />
            </svg>
            Node coverage · defended area
          </li>
          <li>
            <svg viewBox="0 0 16 12" aria-hidden="true">
              <path
                d="M8 1 13 6 8 11 3 6Z"
                fill="none"
                stroke="#ff5a52"
                strokeWidth="1.8"
              />
            </svg>
            Threat
          </li>
          <li>
            <svg viewBox="0 0 16 12" aria-hidden="true">
              <path
                d="M0 6H16"
                stroke="#e9b44c"
                strokeWidth="2"
                strokeDasharray="4 3"
              />
            </svg>
            Proposed response
          </li>
          <li>
            <svg viewBox="0 0 16 12" aria-hidden="true">
              <path
                d="M0 6H16"
                stroke="#5aa9ff"
                strokeWidth="2"
                strokeDasharray="1.5 3"
              />
            </svg>
            Authorized response
          </li>
          <li>
            <svg viewBox="0 0 16 12" aria-hidden="true">
              <path d="M8 1 12 11 8 8.5 4 11Z" fill="#f1f6fb" />
            </svg>
            Interceptor · simulated
          </li>
        </ul>
      </div>
    </div>
  );
}

/** Legend, where the map is centred, the outcome, and the idle hint. */
export function MapOverlay() {
  const { snapshot, location } = useScenario();
  if (!snapshot) return <Legend />;

  const { site } = snapshot;
  const counts = missionCounts(snapshot);
  const located = site.location_source === "DEVICE";
  const where = located
    ? `Centred on your location · ${site.latitude.toFixed(3)}, ${site.longitude.toFixed(3)}`
    : location === "locating"
      ? "Locating you…"
      : "Default location - allow location access to centre on you";

  return (
    <>
      <Legend />
      <div className="c-map-hud c-hud-tr">
        <span
          className={`c-chip c-location${located ? ` ${toneClass("ready")} is-lit` : ""}`}
        >
          {where}
        </span>
      </div>
      {snapshot.state === "COMPLETE" && (
        <div
          className={`c-map-hud c-banner ${toneClass(
            counts.intercepted === counts.threats ? "ready" : "alert",
          )}`}
          role="status"
        >
          Mission complete
          <small>
            {counts.intercepted} of {counts.threats} threats intercepted ·
            simulation only
          </small>
        </div>
      )}
      {snapshot.state === "IDLE" && (
        <div className="c-map-hud c-map-hint">
          Select a threat scenario, then start the demo
        </div>
      )}
    </>
  );
}
