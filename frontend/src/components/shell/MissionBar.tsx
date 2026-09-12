import { describeSituation, formatElapsed, type Tone } from "../../scenario/format";
import { useScenario } from "../../scenario/hooks";
import { missionCounts } from "../../scenario/select";
import { DemoControls } from "./DemoControls";
import { MissionPill } from "./Tone";
import { toneClass } from "./toneClass";

function Counter({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: Tone;
}) {
  const lit = tone !== undefined && value > 0;
  return (
    <li className={`c-counter${lit ? ` is-lit ${toneClass(tone)}` : ""}`}>
      <span className="c-counter-value">{value}</span>
      <span className="c-label">{label}</span>
    </li>
  );
}

/** The whole mission at a glance, what is happening, and the simulation controls. */
export function MissionBar() {
  const { snapshot } = useScenario();
  const counts = snapshot ? missionCounts(snapshot) : null;

  return (
    <footer className="c-timeline">
      <div className="c-timeline-meta">
        <span className="c-label">Mission</span>
        <span className="c-elapsed">{formatElapsed(snapshot?.elapsed_s ?? 0)}</span>
      </div>

      <ul className="c-counters" aria-label="Mission summary">
        <Counter label="Threats" value={counts?.threats ?? 0} />
        <Counter label="Inside area" value={counts?.inside ?? 0} tone="alert" />
        <Counter
          label="Awaiting decision"
          value={counts?.pending ?? 0}
          tone="ready"
        />
        <Counter label="In flight" value={counts?.inFlight ?? 0} tone="armed" />
        <Counter
          label="Intercepted"
          value={counts?.intercepted ?? 0}
          tone="ready"
        />
        <Counter
          label="Reached site"
          value={counts?.reachedSite ?? 0}
          tone="alert"
        />
      </ul>

      <p className="c-situation" role="status">
        {snapshot ? (
          <>
            <MissionPill state={snapshot.state} />
            <span>{describeSituation(snapshot)}</span>
          </>
        ) : (
          <span className="c-dim">Connecting to the defense system…</span>
        )}
      </p>

      <DemoControls />
    </footer>
  );
}
