import { navigate } from "../../app/useRoute";
import { NODE_LABEL, NODE_TONE } from "../../scenario/format";
import { useScenario, useScenarioCommands } from "../../scenario/hooks";
import { findEngagement } from "../../scenario/select";
import { toneClass } from "../shell/toneClass";
import { Inventory } from "./Inventory";

/** The six nodes: state, current threat, inventory. Each opens the launcher view. */
export function NodeList() {
  const snapshot = useScenario().snapshot;
  const { selectNode } = useScenarioCommands();
  const nodes = snapshot?.nodes ?? [];
  const active = nodes.filter((node) => node.state !== "STANDBY").length;

  return (
    <section className="c-panel" aria-label="Defense nodes">
      <div className="c-panel-head">
        <h2 className="c-panel-title">Defense nodes</h2>
        <span className="c-count">{active} active</span>
      </div>
      {!snapshot || nodes.length === 0 ? (
        <p className="c-empty">No node data.</p>
      ) : (
        <ul className="c-rows">
          {nodes.map((node) => {
            const engagement = node.engagement_id
              ? findEngagement(snapshot, node.engagement_id)
              : null;
            const tone = toneClass(NODE_TONE[node.state]);
            return (
              <li key={node.id}>
                <button
                  type="button"
                  className="c-row c-row-button"
                  aria-label={`Open ${node.id} in the launcher view`}
                  onClick={() => {
                    selectNode(node.id);
                    navigate("launcher");
                  }}
                >
                  <span className={`c-node-dot-sm ${tone}`} aria-hidden="true" />
                  <b className="c-row-id">{node.id}</b>
                  <span className={`c-row-status ${tone}`}>
                    {NODE_LABEL[node.state]}
                    {engagement ? ` · ${engagement.track_id}` : ""}
                  </span>
                  <Inventory
                    count={node.inventory}
                    capacity={node.inventory_capacity}
                  />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
