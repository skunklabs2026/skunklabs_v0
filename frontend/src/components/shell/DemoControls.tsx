import { useScenario, useScenarioCommands } from "../../scenario/hooks";

/**
 * The simulation harness: scenario choice, START DEMO and RESET. Deliberately
 * apart from the operator's own controls - it drives the simulated world, not
 * the defense system.
 */
export function DemoControls() {
  const { snapshot, pending, connection } = useScenario();
  const { configure, start, reset } = useScenarioCommands();
  const blocked = connection !== "online" || !snapshot || pending !== null;
  const idle = !snapshot || snapshot.can_start;
  const finished = snapshot?.state === "COMPLETE" || snapshot?.state === "FAULT";

  return (
    <div className="c-demo" role="group" aria-label="Simulation controls">
      <span className="c-label">Simulation</span>
      <select
        className="c-select"
        aria-label="Threat scenario"
        value={snapshot?.scenario_id ?? ""}
        disabled={blocked || !snapshot?.can_configure}
        onChange={(event) => configure({ scenario_id: event.target.value })}
      >
        {snapshot?.scenarios.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </select>
      {idle ? (
        <button
          type="button"
          className="c-btn c-btn-primary c-btn-small"
          disabled={blocked}
          onClick={start}
        >
          {pending === "start" ? "Starting…" : "Start demo"}
        </button>
      ) : (
        <button
          type="button"
          className={`c-btn c-btn-small${finished ? " c-btn-primary" : ""}`}
          disabled={blocked}
          onClick={reset}
        >
          {pending === "reset" ? "Resetting…" : "Reset demo"}
        </button>
      )}
    </div>
  );
}
