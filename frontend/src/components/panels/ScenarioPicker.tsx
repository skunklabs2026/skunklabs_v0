import { plural } from "../../scenario/format";
import { useScenario, useScenarioCommands } from "../../scenario/hooks";

/** The three threat scenarios, chosen before the demo starts. */
export function ScenarioPicker() {
  const { snapshot, pending, connection } = useScenario();
  const { configure } = useScenarioCommands();
  if (!snapshot) return null;
  const locked =
    !snapshot.can_configure || pending !== null || connection !== "online";

  return (
    <section className="c-panel" aria-label="Threat scenario">
      <div className="c-panel-head">
        <h2 className="c-panel-title">Threat scenario</h2>
        <span className="c-chip">Simulated</span>
      </div>
      <div className="c-scenarios" role="radiogroup" aria-label="Threat scenario">
        {snapshot.scenarios.map((option) => (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={option.id === snapshot.scenario_id}
            className="c-scenario"
            disabled={locked}
            onClick={() => configure({ scenario_id: option.id })}
          >
            <b>{option.name}</b>
            <span>{option.description}</span>
            <small>{plural(option.threat_count, "threat")}</small>
          </button>
        ))}
      </div>
      {!snapshot.can_configure && (
        <p className="c-hint">Reset the demo to choose another scenario.</p>
      )}
    </section>
  );
}
